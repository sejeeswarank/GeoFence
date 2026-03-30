# First Launch Checklist

## Before Running

1. Install Python 3.10 or newer on Windows.
2. Reopen PowerShell after installation so the shell can see Python.
3. From `P:\GeoFence`, run:

```powershell
.\setup.ps1
```

## Start The App

Run:

```powershell
.\run.ps1
```

Then open:

```text
http://localhost:8000
```

## Quick Checks

- The dashboard loads without a backend error banner.
- `Preprocess: On` and `Tracking: On` appear in the header.
- The default zone shows as active, or you can draw a new one.
- Clicking `Start Camera` switches the status pill to `LIVE`.
- The feed starts updating and FPS appears in the top-right metadata.
- Detections show an object label, a stable `#id`, and a `safe` or `alert` state.
- The event log grows when an object moves from inside to outside the zone or back again.

## If Something Fails

- `Python 3.10+ was not found`
  Install Python from https://www.python.org/downloads/windows/ and rerun `.\setup.ps1`.

- `No virtual environment found at .venv`
  Run `.\setup.ps1` before `.\run.ps1`.

- `running scripts is disabled on this system`
  Run the helper with a one-time bypass:
  `powershell -ExecutionPolicy Bypass -File .\setup.ps1`
  and
  `powershell -ExecutionPolicy Bypass -File .\run.ps1`

- `Unable to open the camera device`
  Close other apps using the webcam and confirm Windows camera permissions are enabled.

- The first startup is slow
  YOLO may be downloading or warming its model cache on the first run.

- Dependency install fails
  Check internet access and rerun `.\setup.ps1`.

- The dashboard loads but no detections appear
  Confirm the camera is running, the scene contains supported classes, and lighting is good enough for YOLO detection.
