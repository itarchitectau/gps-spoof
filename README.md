# iOS GPS Spoofer

A simple web UI for spoofing the GPS location of a USB-connected iPhone to any Australian suburb.

## How it works

```
index.html  ←─ fetch ─→  server.py (localhost:9876)  ←─ subprocess ─→  pymobiledevice3  ←─ USB ─→  iPhone
```

- **`index.html`** — browser UI: suburb search, map preview, one-click spoof/reset
- **`server.py`** — tiny local HTTP server (stdlib only) that wraps pymobiledevice3
- Manual commands and GPX export work even without the server running

## Prerequisites

- Python 3.9+
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)
- iPhone trusted on the computer, connected via USB

Install pymobiledevice3:

```bash
pip install pymobiledevice3
```

## Quick start

### Mac / Linux

```bash
chmod +x start.sh
./start.sh
```

### Windows

Double-click `start.bat`, or run:

```bat
python server.py
```

Then open `index.html` in your browser.

## Usage

1. Start the server (above).
2. Open `index.html` — the status bar shows server and device connection state.
3. Type a suburb or postcode (e.g. `Bondi Beach`, `Fitzroy`, `3065`).
4. Select a result from the suggestions.
5. Click **Spoof Device** — your iPhone's GPS moves to that location immediately.
6. Click **Reset GPS** to restore the real location.

## Status indicators

| Pill | Meaning |
|---|---|
| Server: online (green) | `server.py` is reachable on `localhost:9876` |
| Device: connected (green) | iPhone detected over USB |
| Spoofing: active (cyan) | A simulated location is currently set |

## Manual fallback

If the server is not running, expand **Manual commands & GPX** in the UI for:

- `pymobiledevice3` terminal command (copy & paste)
- `idevicesetlocation` command (libimobiledevice)
- GPX file download for use with Xcode / iOS Simulator

## iOS version notes

| iOS version | Works with |
|---|---|
| iOS 16 and earlier | `simulate-location` via DVT (default) |
| iOS 17+ | May require `pymobiledevice3 developer dvt` with a Developer Mode + mounted disk image |

If spoofing fails on iOS 17+, run this first to mount the developer disk image:

```bash
python -m pymobiledevice3 mounter auto-mount
```

## Files

```
gps-spoof/
├── index.html   # Web UI
├── server.py    # Local API server
├── start.sh     # Mac / Linux launcher
├── start.bat    # Windows launcher
└── README.md
```

## Security note

The server only listens on `127.0.0.1` (loopback) and is not accessible from other machines on the network.
