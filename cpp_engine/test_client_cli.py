#!/usr/bin/env python3
"""
Phase 1 Test Client / CLI for the isolated C++ Engine (`cpp_engine/').
Connects to ws://127.0.0.1:<port>/ws?token=<token> using zero third-party
dependencies (pure Python socket + RFC 6455 framing), exercises all IPC commands,
and prints real-time telemetry / gate status.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
from typing import Any, Dict


class SimpleLoopbackWsClient:
    """Minimal RFC 6455 WebSocket client restricted to 127.0.0.1."""

    def __init__(self, port: int, token: str, origin: str = "http://127.0.0.1:8000"):
        self.port = port
        self.token = token
        self.origin = origin
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5.0)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET /ws?token={self.token} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Origin: {self.origin}\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(req.encode("utf-8"))
        resp = s.recv(4096).decode("utf-8", errors="replace")
        if "101 Switching Protocols" not in resp:
            s.close()
            raise RuntimeError(f"WebSocket handshake failed: {resp.splitlines()[0] if resp else 'empty'}")
        self.sock = s

    def send_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        assert self.sock is not None
        raw = json.dumps(payload).encode("utf-8")
        mask_key = os.urandom(4)
        header = bytearray([0x81])  # FIN + text frame
        length = len(raw)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            raise ValueError("Frame too large")
        header.extend(mask_key)
        masked = bytearray(b ^ mask_key[i & 3] for i, b in enumerate(raw))
        self.sock.sendall(header + masked)

        # Read server reply frame
        hdr = self._recv_exact(2)
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        body = self._recv_exact(length)
        return json.loads(body.decode("utf-8"))

    def _recv_exact(self, n: int) -> bytes:
        assert self.sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Socket closed while reading WebSocket frame")
            buf.extend(chunk)
        return bytes(buf)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.sendall(b"\x88\x80\x00\x00\x00\x00")
            except OSError:
                pass
            self.sock.close()
            self.sock = None


def run_smoke_suite(host_exe: str, port: int) -> int:
    token = "cli_phase1_verification_token"
    proc = subprocess.Popen(
        [host_exe, "--port", str(port), "--token", token, "--sr", "48000", "--buffer", "128"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(0.4)
        client = SimpleLoopbackWsClient(port=port, token=token)
        client.connect()

        print("1. [PING] ->", client.send_json({"type": "ping", "req_id": "1"}))

        st = client.send_json({"type": "get_state", "req_id": "2"})
        print(f"2. [GET_STATE] -> ok={st.get('ok')} scenes={len(st.get('scenes', []))} params={len(st.get('params', []))}")

        p_norm = client.send_json({
            "type": "set_param",
            "req_id": "3",
            "block": "amp",
            "param": "gain",
            "normalized": 0.82,
        })
        print("3. [SET_PARAM normalized=0.82] ->", p_norm)

        p_val = client.send_json({
            "type": "set_param",
            "req_id": "4",
            "block": "cab",
            "param": "lowcut",
            "value": 100.0,
        })
        print("4. [SET_PARAM LogHz cab.lowcut=100Hz] ->", p_val)

        sc = client.send_json({"type": "set_scene", "req_id": "5", "scene_index": 3})
        print("5. [SET_SCENE D (index 3)] ->", sc)

        time.sleep(0.5)
        metrics = client.send_json({"type": "get_metrics", "req_id": "6"})
        print("6. [GET_METRICS] ->", json.dumps(metrics, indent=2))

        client.close()
        return 0 if metrics.get("gate_check", {}).get("passed") else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hack-Effect C++ Phase 1 Test Client")
    parser.add_argument(
        "--host-exe",
        default=os.path.join(os.path.dirname(__file__), "build", "Release", "hack_effect_host.exe"),
        help="Path to compiled hack_effect_host.exe",
    )
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    return run_smoke_suite(args.host_exe, args.port)


if __name__ == "__main__":
    sys.exit(main())
