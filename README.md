# GeoFence Vision

GeoFence Vision is a modern FastAPI + OpenCV + YOLOv8 app for camera-based geo-fencing. It provides a full security monitoring workspace:

- Core Pipeline: `Camera -> Preprocessing -> YOLO Detection -> Tracking -> Geo Fence Check -> Safe/Alert Event`
- Firebase authentication
- Dedicated login and register pages
- Authenticated dashboard with multi-camera configuration (Local, IP, Mobile, external video files)
- Google Drive persistence for per-user JSON snapshots of settings and event histories

## Project Layout

- `frontend/` - Dashboard and auth HTML (`login.html`, `register.html`, `index.html`), browser JavaScript (`dashboard.js`), and logo assets
- `backend/` - FastAPI app (`main.py`), detection/tracking backend pipeline (`detector.py`, `tracker.py`, `geofence.py`), and backend config files
- `project root` - `.env` templates and PowerShell helper scripts for running/setup

## Prerequisites & Installation

### 1. Before Running
1. Install **Python 3.10** or newer on Windows.
2. Reopen PowerShell after installation so your terminal can find `python`.
3. From the `P:\GeoFence` directory, install all required dependencies (this creates the `.venv` if none exists):

```powershell
.\setup.ps1
```

*(Alternatively, you can manually run `pip install -r backend/requirements.txt` inside your virtual environment).*

## Configuration

### Firebase Setup (Required for Login)

1. Create a Firebase project and enable Email/Password authentication.
2. Add a web app in Firebase and securely copy the public config values into your `.env` or shell environment. Use `.env.example` as a structural template.
3. Download a Firebase Admin service account JSON file and place it in the `backend/` directory or root (e.g. `firebase-admin.json`).
4. Set the path in your `.env` file:
```text
FIREBASE_ADMIN_CREDENTIALS=backend/firebase-admin.json
```

### Google Drive Setup (Optional)

The app stores per-user JSON data in the Google Drive `appDataFolder`, using a file name based on each Firebase user ID.
1. Create a Google Cloud OAuth client for a Desktop App.
2. Save the OAuth client file as `google-drive-oauth-client.json` inside `backend/`.
3. If applicable, run your one-time Drive authorization script (e.g. `& ".\.venv\Scripts\python.exe" backend/drive_setup.py`) to generate the required `google-drive-token.json`.

## Run The App

Start the server using the run script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Then open:
[http://localhost:8000](http://localhost:8000)

## Quick Checks (First Run)

Once logged into the dashboard (`/app`):
- Check that the dashboard loads smoothly without a backend error banner.
- Under **Saved Cameras**, ensure you can connect a new camera profile or select an existing one. Look for the `ACTIVE` pill.
- Verify that `Preprocess: On` and `Tracking: On` logic components are present.
- Click `Use Camera`, assign it a zone if desired, and click `Start Camera` to change the dashboard feed to `LIVE`.
- Verify that the feed starts rendering annotated frames and FPS updates in the top right metadata section.
- Test YOLO detections: When someone or something enters the frame, ensure they're assigned a stable `#id` and state (`safe` or `alert`).
- Monitor the Alert events log: It should register events automatically when objects enter or leave the colored drawn zone.

## Troubleshooting

- **`Python 3.10+ was not found`**: Install Python from [python.org](https://www.python.org/downloads/windows/) and rerun `.\setup.ps1`.
- **`No virtual environment found at .venv`**: You must run `.\setup.ps1` before `.\run.ps1`.
- **`running scripts is disabled on this system`**: Run the scripts with the bypass flag:
   `powershell -ExecutionPolicy Bypass -File .\setup.ps1`
   `powershell -ExecutionPolicy Bypass -File .\run.ps1`
- **`Unable to open the camera device`**: Close other apps (Zoom, Teams) actively using your webcam, and confirm Windows system camera privacy settings are enabled.
- **The first startup is slow**: YOLO may be downloading its model cache or validating the `yolov8n.pt` weights file on the very first frame.
- **The dashboard loads but no detections appear**: Confirm your camera feed is running and that your lighting is adequate. Objects must be clearly visible for YOLO inference.

## Important Backend Flow Notes
- The dashboard page redirects to `/login` if no persistent Firebase session token is verified by the backend SDK (`auth_service.py`).
- If Firebase web config is missing, the frontend will show a configuration message instead of failing completely.
- If Google Cloud Drive sync is inactive, the core local features still work, but you'll receive a descriptive warning if you trigger cloud snapshots.
