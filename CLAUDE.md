# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
# Mac / Linux
python3 server.py

# Windows
python server.py
# or double-click start.bat
```

The server starts on `http://127.0.0.1:9876`. Open `index.html` in a browser alongside it.

## iOS 17+ prerequisite

Before spoofing on iOS 17+, mount the developer disk image once:

```bash
python3 -m pymobiledevice3 mounter auto-mount
```

## Architecture

This is a two-piece tool with no build step:

**`server.py`** — a stdlib-only HTTP server (no Flask/FastAPI). It exposes three endpoints:
- `GET /status` — calls `pymobiledevice3 usbmux list` to detect a connected device; returns `{"connected": bool, "udid": str|null}`
- `POST /spoof` `{"lat": float, "lng": float}` — calls `pymobiledevice3 developer dvt simulate-location set -- LAT LNG`
- `POST /reset` — calls `pymobiledevice3 developer dvt simulate-location clear`

All pymobiledevice3 calls are made via `subprocess.run([sys.executable, "-m", "pymobiledevice3", ...])` so they always use whichever Python environment the server was launched from.

**`index.html`** — self-contained single-page UI (no framework, no bundler). Key behaviours:
- Geocodes suburb/postcode input via the Nominatim API (OpenStreetMap, no API key needed), restricted to `countrycodes=au`
- Polls `localhost:9876/status` every 4 seconds and reflects state in three status pills (server / device / spoofing)
- When the server is unreachable, shows the server-hint panel and disables the Spoof/Reset buttons; manual commands and GPX export remain functional
- GPX files are generated client-side with `URL.createObjectURL` and downloaded directly

## API contract (server ↔ UI)

All responses are `application/json`. On subprocess failure the server returns HTTP 500 with `{"ok": false, "message": "<stderr>"}`. CORS is open (`*`) since the page is served from `file://`.
