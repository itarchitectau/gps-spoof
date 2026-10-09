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
IS_WINDOWS = platform.system() == "Windows"

# Suppress console windows on Windows when spawning subprocesses.
_SUBPROCESS_FLAGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if IS_WINDOWS
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
    """Pull the outermost JSON array or object out of text.

    pymobiledevice3 sometimes emits log/progress lines before the JSON payload.
    We scan for the first '[' or '{' and then find its matching bracket.
    """
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        idx = text.find(start_char)
        if idx == -1:
            continue
        depth = 0
        for i, ch in enumerate(text[idx:], idx):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return text[idx : i + 1]
    return None


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
    """Extract UDID — key name varies across pymobiledevice3 versions."""
    for key in ("Identifier", "SerialNumber", "udid", "UDID"):
        if device.get(key):
            return device[key]
    return None


def check_amds():
    """Windows only: return status of the Apple Mobile Device Service."""
    if not IS_WINDOWS:
        return None
    try:
        r = subprocess.run(
            ["sc", "query", "Apple Mobile Device Service"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if "RUNNING" in r.stdout:
            return "running"
        if "STOPPED" in r.stdout:
            return "stopped"
        return "not_found"
    except Exception:
        return "unknown"


def check_device():
    """Return (connected: bool, udid: str | None, diagnostics: dict)."""
    diag = {}

    # Try usbmux list first, then lockdown list as fallback.
    for cmd in (["usbmux", "list"], ["lockdown", "list"]):
        try:
            r = _run(cmd, timeout=5)
            diag[" ".join(cmd)] = {
                "returncode": r.returncode,
                "stdout": r.stdout[:800],
                "stderr": r.stderr[:400],
            }
            devices = _parse_devices(r.stdout) or _parse_devices(r.stderr)
            if devices:
                return True, _udid(devices[0]), diag
        except FileNotFoundError:
            diag["error"] = "pymobiledevice3 not found — run: pip install pymobiledevice3"
            return False, None, diag
        except subprocess.TimeoutExpired:
            diag[" ".join(cmd)] = {"error": "timed out"}
        except Exception as exc:
            diag[" ".join(cmd)] = {"error": str(exc)}

    if IS_WINDOWS:
        diag["amds"] = check_amds()

    return False, None, diag


def _device_hints(diag):
    """Return a human-readable hint string based on diagnostics."""
    if "error" in diag and "not found" in diag.get("error", ""):
        return "pymobiledevice3 is not installed. Run: pip install pymobiledevice3"

    amds = diag.get("amds")
    if amds == "stopped":
        return "Apple Mobile Device Service is installed but STOPPED. Open Services (services.msc) and start it."
    if amds == "not_found":
        return "Apple Mobile Device Support is not installed. Install iTunes or Apple Devices from the Microsoft Store."

    # Look for clues in command output
    for key in ("usbmux list", "lockdown list"):
        entry = diag.get(key, {})
        combined = entry.get("stdout", "") + entry.get("stderr", "")
        if "trust" in combined.lower():
            return "Your iPhone is asking to trust this computer. Tap 'Trust' on the device."
        if "locked" in combined.lower():
            return "Device is locked. Unlock your iPhone and try again."
        if "permission" in combined.lower() or "access" in combined.lower():
            return "Permission error. Try running the server as Administrator."

    return "Plug in your iPhone via USB and tap 'Trust This Computer' if prompted."


def set_location(lat, lng):
    r = _run(["developer", "dvt", "simulate-location", "set", "--", str(lat), str(lng)])
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def reset_location():
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
            connected, udid, diag = check_device()
            hint = "" if connected else _device_hints(diag)
            self._send_json(200, {"connected": connected, "udid": udid, "hint": hint})

        elif path == "/debug":
            connected, udid, diag = check_device()
            hint = "" if connected else _device_hints(diag)
            self._send_json(200, {
                "connected": connected, "udid": udid,
                "hint": hint, "diagnostics": diag,
            })

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


def startup_diagnostics():
    print(f"\n  GPS spoof server  http://127.0.0.1:{PORT}"
          f"  [{platform.system()} / Python {sys.version.split()[0]}]")

    if IS_WINDOWS:
        amds = check_amds()
        status_label = {"running": "RUNNING", "stopped": "STOPPED — start it in services.msc",
                        "not_found": "NOT INSTALLED — install iTunes or Apple Devices",
                        "unknown": "unknown"}.get(amds, amds)
        print(f"  Apple Mobile Device Service: {status_label}")

    print("  Checking for connected iOS device...")
    connected, udid, diag = check_device()
    if connected:
        print(f"  Device found: {udid}")
    else:
        hint = _device_hints(diag)
        print(f"  No device found. {hint}")
        for cmd_key in ("usbmux list", "lockdown list"):
            entry = diag.get(cmd_key, {})
            if entry.get("stderr", "").strip():
                print(f"  [{cmd_key}] stderr: {entry['stderr'].strip()[:200]}")
            if entry.get("stdout", "").strip():
                print(f"  [{cmd_key}] stdout: {entry['stdout'].strip()[:200]}")

    print(f"\n  Open index.html in your browser.")
    print(f"  Visit http://127.0.0.1:{PORT}/debug for full raw diagnostics.\n")


if __name__ == "__main__":
    startup_diagnostics()
    server = Server(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
