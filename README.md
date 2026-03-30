# GeoFence Vision

GeoFence Vision is a FastAPI + OpenCV + YOLOv8 app for camera-based geo-fencing. It now includes:

- Firebase authentication
- dedicated login and register pages
- an authenticated dashboard
- Google Drive persistence for per-user JSON snapshots
- multi-camera switching

## Main Flow

`Camera -> Preprocessing -> YOLO Detection -> Tracking -> Geo Fence Check -> Safe or Alert -> Display -> Save Snapshot`

## Pages

- `/login` - Firebase sign-in
- `/register` - Firebase account creation
- `/app` - authenticated dashboard

## Features

- Email/password login via Firebase Auth
- Backend Firebase token verification with the Firebase Admin SDK
- Google Drive `appDataFolder` sync keyed by Firebase `uid`
- Camera selection from the dashboard
- Save and restore zone/session snapshots from Drive

## Dependencies

Install with:

```powershell
.\setup.ps1
```

Or manually:

```bash
pip install -r requirements.txt
```

## Firebase Setup

1. Create a Firebase project.
2. Enable Email/Password authentication.
3. Add a web app in Firebase and copy the public config values into `.env` or your shell environment.
4. Download a Firebase Admin service account JSON file and place it in the project root, for example:

```text
firebase-admin.json
```

5. Set:

```text
FIREBASE_ADMIN_CREDENTIALS=firebase-admin.json
```

Use [.env.example](P:\GeoFence\.env.example) as the template for the variables you need.

## Google Drive Setup

1. Create a Google Cloud OAuth client for a desktop app.
2. Save the OAuth client file as:

```text
google-drive-oauth-client.json
```

3. Run the one-time Drive authorization flow:

```powershell
& ".\.venv\Scripts\python.exe" drive_setup.py
```

4. This creates:

```text
google-drive-token.json
```

The app stores per-user JSON data in Google Drive `appDataFolder`, using a file name based on each Firebase user ID.

## Run

Start the server with:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Then open:

```text
http://localhost:8000
```

## Important Files

- [main.py](P:\GeoFence\main.py) - API routes, auth/session endpoints, Drive snapshot endpoints, and camera pipeline
- [auth_service.py](P:\GeoFence\auth_service.py) - Firebase config and backend token verification
- [drive_storage.py](P:\GeoFence\drive_storage.py) - Google Drive load/save logic
- [drive_setup.py](P:\GeoFence\drive_setup.py) - one-time OAuth token generation
- [login.html](P:\GeoFence\login.html) - login page
- [register.html](P:\GeoFence\register.html) - account creation page
- [index.html](P:\GeoFence\index.html) - authenticated dashboard

## Notes

- The dashboard page redirects to `/login` if no Firebase user is signed in.
- If Firebase web config is missing, login and register pages show a configuration error instead of failing silently.
- If Google Drive is not configured yet, the dashboard still works, but Drive save/restore actions return a clear error message.
