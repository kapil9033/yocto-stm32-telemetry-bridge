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


def telemetry_frame(timestamp):
    payload = timestamp.to_bytes(4, "little") + (100).to_bytes(2, "little", signed=True) * 3
    payload += (1234).to_bytes(2, "little") + bytes([22, 45, 1])
    body = bytes([1, len(payload)]) + payload
    crc = crc16(body)
    return encode_cobs(body + bytes([crc & 255, crc >> 8])) + b"\0"


@pytest.mark.integration
def test_daemon_reads_partial_frames_recovers_and_decodes(gateway_binary):
    vector_path = Path(__file__).resolve().parents[1] / "fixtures/protocol_vectors.json"
    vector = json.loads(vector_path.read_text())["telemetry_frame"]
    master, slave = pty.openpty()
    path = os.ttyname(slave)
    process = subprocess.Popen([str(gateway_binary), "--serial", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    os.close(slave)
    try:
        deadline = time.monotonic() + 4
        output = bytearray()
        while time.monotonic() < deadline and b"Connected to" not in output:
            ready, _, _ = select.select([process.stdout], [], [], 0.1)
            if ready:
                output.extend(os.read(process.stdout.fileno(), 4096))
        assert b"Connected to" in output, output.decode(errors="replace")
        frame = telemetry_frame(vector["timestamp_sec"])
        os.write(master, b"\x02\x01bad\0" + frame[:5])
        time.sleep(0.05)
        os.write(master, frame[5:] + telemetry_frame(vector["timestamp_sec"] + 1))
        end = time.monotonic() + 3
        while time.monotonic() < end and output.count(b"[TELEMETRY]") < 2:
            ready, _, _ = select.select([process.stdout], [], [], 0.1)
            if ready:
                output.extend(os.read(process.stdout.fileno(), 4096))
        text = output.decode(errors="replace")
        assert f"Timestamp={vector['timestamp_sec']}" in text
        assert f"Timestamp={vector['timestamp_sec'] + 1}" in text
        assert b"Invalid frame" in output
    finally:
        process.terminate()
        process.wait(timeout=3)
        os.close(master)
