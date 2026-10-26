"""Read-only telemetry continuity and performance checks on the physical Pi/STM32."""

import os
import re
import select
import subprocess
import time

import pytest


JOURNAL_TIME = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s+")
TELEMETRY_MARKER = re.compile(
    r"^([0-9]+(?:\.[0-9]+)?)\s+.*(?:\[TELEMETRY\]\s+Timestamp=|TELEMETRY FRAME RECEIVED)"
)


def ssh(host, command, timeout=15):
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, command],
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def service_state(host):
    result = ssh(
        host,
        "systemctl show gatewayd --property=ActiveState --property=NRestarts "
        "--property=CPUUsageNSec --property=MainPID --no-pager; "
        'pid=$(systemctl show gatewayd --property=MainPID --value); '
        'grep -E "^(VmRSS|VmHWM):" /proc/$pid/status',
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    for line in result.stdout.splitlines():
        if line.startswith("VmRSS:"):
            values["VmRSSKiB"] = line.split()[1]
        elif line.startswith("VmHWM:"):
            values["VmHWMKiB"] = line.split()[1]
    return values


def record_is_complete(record):
    for line in record["lines"]:
        if "[TELEMETRY] Timestamp=" in line:
            return True
        if "TELEMETRY FRAME RECEIVED" not in line and re.search(r"=+\s*$", line):
            return True
    return False


def collect_telemetry_for(host, duration_seconds):
    process = subprocess.Popen(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            host,
            "journalctl -f -n 0 -u gatewayd --no-pager -o short-unix",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    records = []
    pending = b""
    deadline = time.monotonic() + duration_seconds
    drain_deadline = None
    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                if drain_deadline is None:
                    if records and not record_is_complete(records[-1]):
                        drain_deadline = now + 2.0
                    else:
                        break
                elif now >= drain_deadline:
                    break
            readable, _, _ = select.select([process.stdout], [], [], 0.25)
            if not readable:
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            pending += chunk
            lines = pending.split(b"\n")
            pending = lines.pop()
            for raw_line in lines:
                line = raw_line.decode("utf-8", errors="replace")
                match = TELEMETRY_MARKER.search(line)
                if match:
                    journal_time = JOURNAL_TIME.match(line)
                    records.append({
                        "timestamp": float(match.group(1)),
                        "journal_time": journal_time.group(1) if journal_time else "",
                        "lines": [line],
                    })
                elif records:
                    journal_time = JOURNAL_TIME.match(line)
                    if journal_time and journal_time.group(1) == records[-1]["journal_time"]:
                        records[-1]["lines"].append(line)
        if pending:
            final_line = pending.decode("utf-8", errors="replace")
            match = TELEMETRY_MARKER.search(final_line)
            if match:
                journal_time = JOURNAL_TIME.match(final_line)
                records.append({
                    "timestamp": float(match.group(1)),
                    "journal_time": journal_time.group(1) if journal_time else "",
                    "lines": [final_line],
                })
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
    return [record for record in records if record_is_complete(record)]


def assert_telemetry_fields(record):
    text = "\n".join(record["lines"])
    modern_accel = re.search(r"Accel_mg=(-?\d+),(-?\d+),(-?\d+)", text)
    legacy_accel = re.search(
        r"Accel X / Y / Z\s*:\s*(-?\d+)\s*mg\s*\|\s*(-?\d+)\s*mg\s*\|\s*(-?\d+)\s*mg",
        text,
    )
    acceleration = modern_accel or legacy_accel
    assert acceleration, f"Telemetry record has no parseable X/Y/Z acceleration fields:\n{text}"
    assert all(-32768 <= int(value) <= 32767 for value in acceleration.groups())

    modern_adc = re.search(r"\bADC=(\d+)", text)
    legacy_adc = re.search(r"Photocell Raw\s*:\s*(\d+)\s*/\s*(\d+)", text)
    adc_value = int(modern_adc.group(1)) if modern_adc else int(legacy_adc.group(1)) if legacy_adc else None
    assert adc_value is not None, f"Telemetry record has no ADC field:\n{text}"
    assert 0 <= adc_value <= 4095, f"ADC value outside 12-bit range: {adc_value}"

    modern_button = re.search(r"\bButton=(\d+)", text)
    legacy_button = re.search(r"EXTI Button State\s*:\s*(PRESSED|RELEASED)", text)
    assert modern_button or legacy_button, f"Telemetry record has no button state:\n{text}"
    if modern_button:
        assert int(modern_button.group(1)) in (0, 1)

    dht_error = "DHT11=READ_ERROR" in text
    modern_dht = re.search(r"Temperature_C=(-?\d+)\s+Humidity_pct=(\d+)", text)
    legacy_temp = re.search(r"Temperature\s*:\s*(-?\d+)\s*°?C", text)
    legacy_humidity = re.search(r"Humidity\s*:\s*(\d+)\s*%", text)
    assert dht_error or modern_dht or (legacy_temp and legacy_humidity), (
        f"Telemetry record has neither DHT11 values nor the documented read-error sentinel:\n{text}"
    )
    if modern_dht:
        assert -128 <= int(modern_dht.group(1)) <= 127
        assert 0 <= int(modern_dht.group(2)) <= 100
    if legacy_temp:
        assert -128 <= int(legacy_temp.group(1)) <= 127
    if legacy_humidity:
        assert 0 <= int(legacy_humidity.group(1)) <= 100


@pytest.mark.hil
def test_hil_telemetry_continuity_rate_and_service_stability(record_property):
    """Observe real STM32 frames via the Pi journal without changing target state."""
    host = os.environ.get("YOCTO_SSH_HOST")
    if not host:
        pytest.skip("Set YOCTO_SSH_HOST to run physical Pi/STM32 HIL checks")

    duration = float(os.environ.get("YOCTO_HIL_DURATION_SEC", "60"))
    minimum_rate = float(os.environ.get("YOCTO_HIL_MIN_RATE_HZ", "0.8"))
    maximum_gap = float(os.environ.get("YOCTO_HIL_MAX_GAP_SECONDS", "3.0"))
    if duration < 10:
        pytest.fail("YOCTO_HIL_DURATION_SEC must be at least 10 seconds")

    before = service_state(host)
    assert before.get("ActiveState") == "active", f"gatewayd was not active before capture: {before}"
    assert "NRestarts" in before, f"Could not read gatewayd restart count: {before}"

    telemetry_records = collect_telemetry_for(host, duration)
    after = service_state(host)

    assert after.get("ActiveState") == "active", f"gatewayd was not active after capture: {after}"
    assert after.get("NRestarts") == before["NRestarts"], (
        f"gatewayd restarted during the {duration:g}s observation: "
        f"{before['NRestarts']} -> {after.get('NRestarts')}"
    )
    assert len(telemetry_records) >= 2, (
        f"Only {len(telemetry_records)} telemetry frames appeared in {duration:g}s; "
        "check the STM32 link and gateway journal"
    )

    for record in telemetry_records:
        assert_telemetry_fields(record)
    telemetry_times = [record["timestamp"] for record in telemetry_records]
    intervals = [right - left for left, right in zip(telemetry_times, telemetry_times[1:])]
    observed_span = telemetry_times[-1] - telemetry_times[0]
    observed_rate = (len(telemetry_records) - 1) / observed_span if observed_span > 0 else 0.0
    longest_gap = max(intervals)
    cpu_delta_ns = int(after["CPUUsageNSec"]) - int(before["CPUUsageNSec"])
    assert cpu_delta_ns >= 0, f"Gateway CPU counter decreased during observation: {cpu_delta_ns} ns"
    average_cpu_percent = cpu_delta_ns / (duration * 1_000_000_000) * 100.0
    record_property("observation_seconds", f"{duration:g}")
    record_property("telemetry_frames", str(len(telemetry_records)))
    record_property("frames_with_valid_fields", str(len(telemetry_records)))
    record_property("observed_rate_hz", f"{observed_rate:.3f}")
    record_property("longest_gap_seconds", f"{longest_gap:.3f}")
    record_property("gateway_restarts", after["NRestarts"])
    record_property("average_cpu_percent_of_one_core", f"{average_cpu_percent:.2f}")
    record_property("rss_kib_start_end", f"{before['VmRSSKiB']} -> {after['VmRSSKiB']}")
    record_property("process_high_water_rss_kib", after["VmHWMKiB"])
    record_property("criteria", f">={minimum_rate:g} Hz; gap <={maximum_gap:g} s; no service restart")

    assert observed_rate >= minimum_rate, (
        f"Observed {observed_rate:.3f} telemetry frames/s; required screening rate is "
        f"{minimum_rate:g} frames/s over {duration:g}s"
    )
    assert longest_gap <= maximum_gap, (
        f"Longest telemetry gap was {longest_gap:.3f}s; screening limit is {maximum_gap:g}s"
    )
