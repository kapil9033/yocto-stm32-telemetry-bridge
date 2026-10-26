import os
import json
import pty
import select
import subprocess
import time
from pathlib import Path

import pytest


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def encode_cobs(data):
    result = bytearray([0])
    code_index, code = 0, 1
    for byte in data:
        if byte == 0:
            result[code_index] = code
            code_index = len(result)
            result.append(0)
            code = 1
        else:
            result.append(byte)
            code += 1
            if code == 0xFF:
                result[code_index] = code
                code_index = len(result)
                result.append(0)
                code = 1
    result[code_index] = code
    return bytes(result)


def frame(message_type, payload):
    body = bytes([message_type, len(payload)]) + payload
    crc = crc16(body)
    return encode_cobs(body + bytes([crc & 255, crc >> 8])) + b"\0"


def telemetry_payload(timestamp):
    payload = timestamp.to_bytes(4, "little") + (100).to_bytes(2, "little", signed=True) * 3
    return payload + (1234).to_bytes(2, "little") + bytes([22, 45, 1])


def telemetry_frame(timestamp):
    return frame(1, telemetry_payload(timestamp))


def wait_for_output(process, output, marker, timeout=4, count=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and output.count(marker) < count:
        if process.poll() is not None:
            break
        ready, _, _ = select.select([process.stdout], [], [], 0.1)
        if ready:
            output.extend(os.read(process.stdout.fileno(), 4096))
    return output.count(marker) >= count


def start_gateway(gateway_binary, serial_path):
    return subprocess.Popen(
        [str(gateway_binary), "--serial", str(serial_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


@pytest.mark.integration
def test_daemon_reads_partial_frames_recovers_and_decodes(gateway_binary):
    vector_path = Path(__file__).resolve().parents[1] / "fixtures/protocol_vectors.json"
    vector = json.loads(vector_path.read_text())["telemetry_frame"]
    master, slave = pty.openpty()
    path = os.ttyname(slave)
    process = start_gateway(gateway_binary, path)
    os.close(slave)
    try:
        output = bytearray()
        assert wait_for_output(process, output, b"Connected to"), output.decode(errors="replace")
        frame = telemetry_frame(vector["timestamp_sec"])
        os.write(master, b"\x02\x01bad\0" + frame[:5])
        time.sleep(0.05)
        os.write(master, frame[5:] + telemetry_frame(vector["timestamp_sec"] + 1))
        wait_for_output(process, output, b"[TELEMETRY]", timeout=3, count=2)
        text = output.decode(errors="replace")
        assert f"Timestamp={vector['timestamp_sec']}" in text
        assert f"Timestamp={vector['timestamp_sec'] + 1}" in text
        assert b"Invalid frame" in output
    finally:
        process.terminate()
        process.wait(timeout=3)
        os.close(master)


@pytest.mark.integration
def test_daemon_discards_oversized_frame_then_recovers(gateway_binary):
    master, slave = pty.openpty()
    process = start_gateway(gateway_binary, os.ttyname(slave))
    os.close(slave)
    try:
        output = bytearray()
        assert wait_for_output(process, output, b"Connected to"), output.decode(errors="replace")
        timestamp = 1700000200
        os.write(master, b"x" * 513 + b"\0" + telemetry_frame(timestamp))
        assert wait_for_output(process, output, b"[TELEMETRY]", timeout=4)
        text = output.decode(errors="replace")
        assert "Encoded frame exceeds maximum size" in text
        assert f"Timestamp={timestamp}" in text
    finally:
        process.terminate()
        process.wait(timeout=3)
        os.close(master)


@pytest.mark.integration
def test_daemon_ignores_unknown_type_and_wrong_payload_size(gateway_binary):
    master, slave = pty.openpty()
    process = start_gateway(gateway_binary, os.ttyname(slave))
    os.close(slave)
    try:
        output = bytearray()
        assert wait_for_output(process, output, b"Connected to"), output.decode(errors="replace")
        valid_timestamp = 1700000300
        os.write(master, frame(0x7F, telemetry_payload(valid_timestamp)))
        os.write(master, frame(1, b"short"))
        os.write(master, telemetry_frame(valid_timestamp))
        assert wait_for_output(process, output, b"[TELEMETRY]", timeout=3)
        time.sleep(0.15)
        ready, _, _ = select.select([process.stdout], [], [], 0.1)
        if ready:
            output.extend(os.read(process.stdout.fileno(), 4096))
        text = output.decode(errors="replace")
        assert text.count("[TELEMETRY]") == 1
        assert f"Timestamp={valid_timestamp}" in text
    finally:
        process.terminate()
        process.wait(timeout=3)
        os.close(master)


@pytest.mark.integration
def test_daemon_reconnects_when_serial_device_appears(gateway_binary, tmp_path):
    master, slave = pty.openpty()
    slave_path = os.ttyname(slave)
    os.close(slave)
    delayed_device = tmp_path / "serial-device"
    process = start_gateway(gateway_binary, delayed_device)
    try:
        output = bytearray()
        assert wait_for_output(process, output, b"Retrying connection", timeout=3), output.decode(errors="replace")
        os.symlink(slave_path, delayed_device)
        assert wait_for_output(process, output, b"Connected to", timeout=4), output.decode(errors="replace")
        timestamp = 1700000400
        os.write(master, telemetry_frame(timestamp))
        assert wait_for_output(process, output, b"[TELEMETRY]", timeout=3)
        assert f"Timestamp={timestamp}" in output.decode(errors="replace")
    finally:
        process.terminate()
        process.wait(timeout=3)
        os.close(master)
