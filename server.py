#!/usr/bin/env python3
"""
Local GPS spoof server — bridges the web UI to pymobiledevice3.

Usage:
    python server.py

Then open index.html in your browser and plug in your iPhone via USB.
"""

import json
import platform
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

PORT = 9876

# Suppress console windows on Windows when spawning subprocesses.
_SUBPROCESS_FLAGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if platform.system() == "Windows"
    else {}
)


def _run(args, timeout=10):
    return subprocess.run(
        [sys.executable, "-m", "pymobiledevice3"] + args,
        capture_output=True,
        # Force UTF-8 explicitly — Windows defaults to cp1252 with text=True.
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        **_SUBPROCESS_FLAGS,
    )


def _extract_json(text):
    """Pull the first JSON array or object out of text.

    pymobiledevice3 sometimes emits log/progress lines before the JSON payload,
    especially on Windows, so we can't parse stdout directly.
    """
    match = re.search(r'(\[.*?\]|\{.*?\})', text, re.DOTALL)
    return match.group(1) if match else None


def _parse_devices(text):
    """Return list of device dicts parsed from raw pymobiledevice3 output."""
    raw = _extract_json(text)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _udid(device):
    """Extract UDID from a device dict — key name varies across versions."""
    for key in ("Identifier", "SerialNumber", "udid", "UDID"):
        if device.get(key):
            return device[key]
    return None


def check_device():
    """Return (connected: bool, udid: str | None, diagnostics: dict)."""
    diag = {}
    try:
        r = _run(["usbmux", "list"], timeout=5)
        diag = {
            "command": "usbmux list",
            "returncode": r.returncode,
            "stdout": r.stdout[:500],
            "stderr": r.stderr[:500],
        }
        # Check stdout first, then stderr (output destination varies by version/OS)
        devices = _parse_devices(r.stdout) or _parse_devices(r.stderr)
        if devices:
            return True, _udid(devices[0]), diag
        # Non-zero exit or empty list — log and report not connected
        if r.returncode != 0:
            print(f"  [device check] returncode={r.returncode}")
        if r.stderr.strip():
            print(f"  [device check] stderr: {r.stderr.strip()[:200]}")
        if r.stdout.strip():
            print(f"  [device check] stdout: {r.stdout.strip()[:200]}")
        return False, None, diag
    except FileNotFoundError:
        msg = "pymobiledevice3 not found — is it installed in this Python environment?"
        print(f"  [device check] {msg}")
        diag["error"] = msg
        return False, None, diag
    except Exception as exc:
        print(f"  [device check] unexpected error: {exc}")
        diag["error"] = str(exc)
        return False, None, diag


def set_location(lat, lng):
    """Simulate GPS location on the connected device."""
    r = _run(["developer", "dvt", "simulate-location", "set", "--", str(lat), str(lng)])
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def reset_location():
    """Restore real GPS on the connected device."""
    r = _run(["developer", "dvt", "simulate-location", "clear"])
    return r.returncode == 0, (r.stderr or r.stdout).strip()


class Server(HTTPServer):
    def handle_error(self, request, client_address):
        # Suppress harmless mid-poll disconnections (common on Windows).
        if sys.exc_info()[0] in (BrokenPipeError, ConnectionResetError):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/status":
            connected, udid, _ = check_device()
            self._send_json(200, {"connected": connected, "udid": udid})

        elif path == "/debug":
            # Returns raw pymobiledevice3 output — useful for diagnosing detection issues.
            connected, udid, diag = check_device()
            self._send_json(200, {"connected": connected, "udid": udid, "diagnostics": diag})

        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/spoof":
            lat = body.get("lat")
            lng = body.get("lng")
            if lat is None or lng is None:
                self._send_json(400, {"error": "lat and lng are required"})
                return
            ok, msg = set_location(lat, lng)
            self._send_json(200 if ok else 500, {"ok": ok, "message": msg})

        elif path == "/reset":
            ok, msg = reset_location()
            self._send_json(200 if ok else 500, {"ok": ok, "message": msg})

        else:
            self._send_json(404, {"error": "not found"})


if __name__ == "__main__":
    server = Server(("127.0.0.1", PORT), Handler)
    print(f"\n  GPS spoof server  http://127.0.0.1:{PORT}  [{platform.system()} / Python {sys.version.split()[0]}]")
    print("  Open index.html, plug in your iPhone, then search for a suburb.")
    print("  Visit http://127.0.0.1:9876/debug for raw device detection output.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
