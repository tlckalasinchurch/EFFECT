"""Minimal RFC 6455 client for the native C++ host (loopback only).

Used by the desktop launcher and Phase 7 acceptance checks to read the
*actual* host backend/latency instead of inventing ASIO UX1 numbers.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
from typing import Any, Dict, Optional, List


class CppHostClient:
    """Connects to ws://127.0.0.1:<port>/ws?token=<token>."""

    def __init__(self, port: int, token: str, origin: str = "http://127.0.0.1:8000"):
        self.port = int(port)
        self.token = str(token)
        self.origin = origin
        self.sock: Optional[socket.socket] = None

    def connect(self, timeout: float = 2.0) -> None:
        s = socket.create_connection(("127.0.0.1", self.port), timeout=timeout)
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
            first = resp.splitlines()[0] if resp else "empty"
            raise RuntimeError(f"WebSocket handshake failed: {first}")
        self.sock = s

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def send_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.sock is None:
            raise RuntimeError("not connected")
        raw = json.dumps(payload).encode("utf-8")
        mask_key = os.urandom(4)
        header = bytearray([0x81])
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

        hdr = self._recv_exact(2)
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        body = self._recv_exact(length)
        return json.loads(body.decode("utf-8"))

    def get_state(self) -> Dict[str, Any]:
        return self.send_json({"type": "get_state", "req_id": "state"})

    def get_metrics(self) -> Dict[str, Any]:
        return self.send_json({"type": "get_metrics", "req_id": "metrics"})

    def _recv_exact(self, n: int) -> bytes:
        assert self.sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RuntimeError("socket closed")
            buf.extend(chunk)
        return bytes(buf)


def find_cpp_host_binary(root: Optional[str] = None) -> Optional[str]:
    """Return the first existing native host binary, or None."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names: List[str] = [
        os.path.join("cpp_engine", "build", "Release", "hack_effect_host.exe"),
        os.path.join("cpp_engine", "build", "RelWithDebInfo", "hack_effect_host.exe"),
        os.path.join("cpp_engine", "build", "Debug", "hack_effect_host.exe"),
        os.path.join("cpp_engine", "build", "hack_effect_host"),
        os.path.join("cpp_engine", "build", "Release", "hack_effect_host"),
    ]
    for rel in names:
        path = os.path.join(root, rel)
        check = os.X_OK if os.name != "nt" else os.F_OK
        if os.path.isfile(path) and os.access(path, check):
            return path
    return None


def snapshot_host(port: int, token: str, timeout: float = 2.0) -> Dict[str, Any]:
    """Return a JSON-serialisable view of the live C++ host, or raise."""
    client = CppHostClient(port, token)
    try:
        client.connect(timeout=timeout)
        state = client.get_state()
        metrics = client.get_metrics()
    finally:
        client.close()

    backend = str(state.get("backend") or metrics.get("backend") or "")
    asio_running = bool(state.get("asio_running") or metrics.get("asio_running"))
    roundtrip = state.get("roundtrip_latency_ms", metrics.get("roundtrip_latency_ms"))
    try:
        roundtrip_f = float(roundtrip) if roundtrip is not None else None
    except (TypeError, ValueError):
        roundtrip_f = None
    if roundtrip_f == 0.0 and not asio_running:
        roundtrip_f = None

    in_lat = state.get("asio_input_latency_samples", metrics.get("asio_input_latency_samples"))
    out_lat = state.get("asio_output_latency_samples", metrics.get("asio_output_latency_samples"))
    sr = int(state.get("sample_rate") or metrics.get("sample_rate") or 0)
    in_ms = (float(in_lat) / sr * 1000.0) if (in_lat and sr) else None
    out_ms = (float(out_lat) / sr * 1000.0) if (out_lat and sr) else None

    return {
        "backend": backend,
        "asio_running": asio_running,
        "asio_driver": state.get("asio_driver") or metrics.get("asio_driver") or "",
        "sample_rate": sr,
        "buffer_size": int(state.get("buffer_size") or metrics.get("buffer_size") or 0),
        "roundtrip_latency_ms": roundtrip_f,
        "input_latency_samples": int(in_lat) if in_lat else 0,
        "output_latency_samples": int(out_lat) if out_lat else 0,
        "input_ms": round(in_ms, 2) if in_ms is not None else None,
        "output_ms": round(out_ms, 2) if out_ms is not None else None,
        "global_bypass": bool(state.get("global_bypass")),
        "using_nam": bool(state.get("using_nam") or metrics.get("using_nam")),
        "is_running": bool(state.get("is_running") or metrics.get("is_running")),
        "metrics": {
            "callback_count": metrics.get("callback_count"),
            "avg_ms": metrics.get("avg_ms"),
            "p99_ms": metrics.get("p99_ms"),
            "xruns": metrics.get("xruns"),
            "callback_errors": metrics.get("callback_errors"),
            "nonfinite_blocks": metrics.get("nonfinite_blocks"),
        },
    }
