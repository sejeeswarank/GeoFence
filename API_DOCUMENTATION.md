# GeoFence Vision — API Documentation

**Live API Docs:** https://geofence-ai.onrender.com/docs  
**Version:** 3.0.0  
**Framework:** FastAPI (Python)  
**Author:** Sejeeswaran K

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Modules](#modules)
4. [API Endpoints](#api-endpoints)
   - [Auth](#auth-endpoints)
   - [Camera](#camera-endpoints)
   - [Geo Fence Zone](#geo-fence-zone-endpoints)
   - [Alerts](#alert-endpoints)
   - [Storage](#storage-endpoints)
   - [System](#system-endpoints)
5. [Design Principles](#design-principles)

---

## Project Overview

**GeoFence Vision** is a real-time AI-powered geo-fencing system. It uses **YOLOv8** to detect objects (people, animals, birds) from a live camera feed and triggers **alerts** when detected objects move outside a user-defined polygon zone.

Key capabilities:
- Real-time object detection via YOLOv8
- Polygon-based geo-fence zone management
- Centroid-based object tracking (stable IDs across frames)
- Firebase Authentication (login/register)
- Google Drive sync for user zone data
- Support for Local Webcam, IP Camera (RTSP), and Mobile camera sources

---

## System Architecture

```
Camera Input (Webcam / RTSP / Mobile)
        ↓
  Frame Preprocessing (CLAHE + Gaussian Blur)
        ↓
  YOLOv8 Object Detection
        ↓
  Centroid Tracker (Stable Object IDs)
        ↓
  GeoFence Zone Check (Shapely Polygon)
        ↓
  Alert Manager (safe / alert status changes)
        ↓
  FastAPI Backend → Frontend Dashboard (Browser)
```

---

## Modules

### `detector.py` — YOLOv8 Object Detector
Wraps the YOLOv8 model. Loads the model on startup and runs inference on each frame. Filters by confidence threshold and target object classes (person, dog, cat, bird, etc.).

**Design decision:** Only tracks specific COCO classes relevant to geo-fencing use cases (animals and humans). All other classes are ignored to reduce noise.

---

### `geofence.py` — Polygon Zone Manager
Manages the geo-fence polygon using **Shapely**. Accepts a list of `[x, y]` points, creates a polygon, and provides `is_inside(x, y)` to check if an object's center point falls within the zone.

**Design decision:** Uses Shapely's `covers()` method (not `contains()`) so objects touching the boundary are considered inside — more forgiving for real-time edge cases.

---

### `tracker.py` — Centroid Object Tracker
Assigns stable numeric IDs to detected objects across frames using centroid distance matching. If an object moves less than `TRACKING_MAX_DISTANCE` pixels between frames, it keeps the same ID.

**Design decision:** Sorts detections by confidence before matching so high-confidence detections get priority in ID assignment. Objects missing for more than `TRACKING_MAX_MISSES` frames are dropped.

---

### `alerts.py` — Alert Manager
Monitors `zone_status` changes for each tracked object. Logs an event only when an object **transitions** between `safe` and `alert` states (not on every frame). Implements a cooldown (`ALERT_COOLDOWN_SECONDS`) to prevent duplicate alerts.

**Design decision:** Uses `deque(maxlen=200)` for O(1) append and automatic eviction of old alerts without manual cleanup.

---

### `preprocessing.py` — Frame Preprocessor
Applies CLAHE (Contrast Limited Adaptive Histogram Equalization) on the L channel of LAB color space to enhance low-light frames, followed by a mild Gaussian blur to reduce noise before YOLO inference.

**Design decision:** Preprocessing is done on the LAB color space (not RGB/BGR) so only the lightness channel is enhanced — avoids color distortion while improving detection in poor lighting.

---

### `auth_service.py` — Firebase Auth
Verifies Firebase ID tokens sent in the `Authorization: Bearer <token>` header. Used to protect storage endpoints. Returns decoded user info (uid, email, name).

---

### `drive_storage.py` — Google Drive Storage
Saves and loads user zone snapshots to Google Drive's `appDataFolder`. Uses OAuth2 for user authorization.

---

### `config.py` — Central Configuration
All tunable parameters in one place: camera settings, YOLO model selection, confidence threshold, tracked classes, preprocessing toggles, tracking parameters, alert cooldown, etc.

---

## API Endpoints

Base URL: `https://geofence-ai.onrender.com`  
Interactive Docs: `https://geofence-ai.onrender.com/docs`

---

### Auth Endpoints

#### `GET /auth/firebase-config`
Returns the Firebase web SDK configuration needed by the frontend to initialize Firebase Auth.

**Response:**
```json
{
  "configured": true,
  "config": {
    "apiKey": "...",
    "authDomain": "...",
    "projectId": "..."
  },
  "message": null
}
```

---

#### `GET /auth/session`
Returns the currently authenticated user's info and Google Drive connection status.

**Headers:** `Authorization: Bearer <firebase_id_token>`

**Response:**
```json
{
  "user": {
    "uid": "abc123",
    "email": "user@example.com",
    "name": "Sejeeswaran",
    "email_verified": true
  },
  "drive": {
    "configured": true,
    "message": "Google Drive is ready."
  }
}
```

---

#### `GET /auth/drive/connect`
Redirects the user to Google's OAuth consent screen to authorize Google Drive access.

---

#### `GET /auth/drive/callback`
OAuth callback endpoint. Exchanges the authorization code for tokens and saves them. Redirects to `/app` on success.

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `code` | string | OAuth authorization code returned by Google |

---

### Camera Endpoints

#### `POST /camera/control`
Start or stop the camera processing loop.

**Request Body:**
```json
{
  "action": "start",
  "source_type": "local",
  "source_url": null
}
```

| Field | Type | Values | Description |
|---|---|---|---|
| `action` | string | `"start"` / `"stop"` | Start or stop the camera |
| `source_type` | string | `"local"` / `"ip"` / `"mobile"` | Camera source type |
| `source_url` | string / null | RTSP or HTTP URL | Required for IP/mobile sources |

**Response:**
```json
{ "status": "started" }
```

---

#### `POST /camera/set-source`
Set the camera source type and URL without starting the camera.

**Request Body:**
```json
{
  "source_type": "ip",
  "source_url": "rtsp://192.168.1.10:8554/stream"
}
```

**Response:**
```json
{
  "status": "ok",
  "source_type": "ip",
  "source_url": "rtsp://192.168.1.10:8554/stream"
}
```

---

#### `GET /camera/options`
Lists all available local cameras detected on the system.

**Response:**
```json
{
  "selected_camera_index": 0,
  "cameras": [
    { "index": 0, "label": "Camera 0", "selected": true }
  ]
}
```

---

#### `POST /camera/select`
Switch to a different local camera by index. Automatically restores that camera's saved zone.

**Request Body:**
```json
{ "camera_index": 1 }
```

**Response:**
```json
{
  "status": "selected",
  "selected_camera_index": 1,
  "restarted": false
}
```

---

#### `GET /camera/frame`
Returns the latest processed camera frame (base64 JPEG), current FPS, and active detections. Called repeatedly by the frontend to render the live feed.

**Response:**
```json
{
  "frame": "<base64_jpeg_string>",
  "fps": 14.3,
  "detections": [
    {
      "label": "person",
      "confidence": 0.91,
      "bbox": [120, 80, 300, 420],
      "center": [210, 250],
      "object_id": 3,
      "inside_zone": false,
      "zone_status": "alert"
    }
  ]
}
```

**Detection zone_status values:**
- `"safe"` — object is inside the geo-fence zone
- `"alert"` — object is outside the geo-fence zone
- `"no-zone"` — no zone is currently configured

---

### Geo Fence Zone Endpoints

#### `GET /zone`
Returns the currently active geo-fence zone configuration.

**Response:**
```json
{
  "active": true,
  "name": "Entrance Zone",
  "points": [[100,100],[400,100],[400,320],[100,320]],
  "area_px": 96000
}
```

---

#### `POST /zone`
Set a new geo-fence polygon zone. Requires at least 3 points.

**Request Body:**
```json
{
  "points": [[100,100],[400,100],[400,320],[100,320]],
  "name": "Entrance Zone"
}
```

| Field | Type | Description |
|---|---|---|
| `points` | array of [x,y] | Minimum 3 polygon vertices in pixel coordinates |
| `name` | string | Display name for the zone |

**Response:**
```json
{
  "status": "zone updated",
  "zone": {
    "active": true,
    "name": "Entrance Zone",
    "points": [[100,100],[400,100],[400,320],[100,320]],
    "area_px": 96000
  }
}
```

---

#### `DELETE /zone`
Clears the active geo-fence zone. Detection continues but no alerts are triggered without a zone.

**Response:**
```json
{ "status": "zone cleared" }
```

---

#### `GET /zones/presets`
Lists all saved zone presets for a specific camera.

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `camera_index` | int (optional) | Defaults to currently selected camera |

**Response:**
```json
{
  "camera_index": 0,
  "active_zone": { "name": "Entrance Zone", "points": [[100,100],[400,100],[400,320],[100,320]] },
  "zones": [
    { "name": "Entrance Zone", "points": [[100,100],[400,100],[400,320],[100,320]] },
    { "name": "Parking Lot", "points": [[50,50],[300,50],[300,200],[50,200]] }
  ]
}
```

---

#### `POST /zones/presets`
Save a named zone preset for a specific camera.

**Request Body:**
```json
{
  "name": "Parking Lot",
  "points": [[50,50],[300,50],[300,200],[50,200]],
  "camera_index": 0
}
```

---

#### `DELETE /zones/presets`
Delete a saved zone preset by name.

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `name` | string | Name of the zone preset to delete |
| `camera_index` | int (optional) | Defaults to currently selected camera |

---

### Alert Endpoints

#### `GET /alerts`
Returns the most recent alert events.

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Maximum number of alerts to return |

**Response:**
```json
{
  "alerts": [
    {
      "id": 12,
      "object_id": "3",
      "label": "person",
      "event": "alert",
      "confidence": 0.91,
      "position": { "x": 210, "y": 250 },
      "timestamp": "2026-03-31T14:22:05",
      "zone": "Entrance Zone"
    }
  ]
}
```

**Event types:**
- `"alert"` — object moved **outside** the geo-fence zone
- `"safe"` — object moved **inside** the geo-fence zone

---

#### `DELETE /alerts`
Clears all stored alert events.

**Response:**
```json
{ "status": "alerts cleared" }
```

---

### Storage Endpoints

> All storage endpoints require Firebase authentication.  
> **Required Header:** `Authorization: Bearer <firebase_id_token>`

#### `POST /storage/snapshot`
Saves the current session state (zone config, alerts, camera settings) to the authenticated user's Google Drive.

**Request Body:**
```json
{ "profile": {} }
```

**Response:**
```json
{
  "status": "saved",
  "snapshot": { ... },
  "file": { "id": "...", "name": "geofence-user-abc123.json", "modifiedTime": "..." }
}
```

---

#### `GET /storage/snapshot`
Loads the user's previously saved snapshot from Google Drive without applying it.

**Response:**
```json
{
  "status": "loaded",
  "snapshot": { ... }
}
```

---

#### `POST /storage/restore`
Loads the snapshot from Google Drive and **applies** it to the current session (restores zone, camera index, and alert history).

**Response:**
```json
{
  "status": "restored",
  "snapshot": { ... },
  "zone": { "active": true, "name": "Entrance Zone", ... }
}
```

---

### System Endpoints

#### `GET /status`
Returns the full system status in one call. Useful for health checks and dashboard initialization.

**Response:**
```json
{
  "camera_running": true,
  "selected_camera_index": 0,
  "saved_zone_count": 2,
  "fps": 14.3,
  "zone_active": true,
  "zone_name": "Entrance Zone",
  "total_alerts": 27,
  "active_detections": 2,
  "tracking_enabled": true,
  "preprocessing_enabled": true,
  "last_error": null
}
```

---

## Design Principles

### 1. Building is primary, documentation is mandatory
The system is fully implemented and working before documentation was written. But documentation is treated as a first-class deliverable — not an afterthought. Every endpoint, module, and design decision is documented so any developer can understand, extend, or question the system confidently.

### 2. One responsibility per module
Each module does exactly one thing — `detector.py` detects, `tracker.py` tracks, `geofence.py` checks zones, `alerts.py` manages events. No module crosses into another's responsibility. This makes the pipeline easy to swap or upgrade (e.g. replace YOLOv8 with a newer model without touching geofence logic).

### 3. Alert on transition, not on every frame
Alerts fire only when an object **changes** zone status (safe → alert or alert → safe). If an object stays outside the zone for 100 frames, only 1 alert is logged. This prevents flooding the event log and makes alerts meaningful.

### 4. Cooldown per object per status
Each `(object_id, status)` pair has its own independent cooldown timer. This handles fast-moving objects gracefully without suppressing legitimate re-entry alerts from other objects.

### 5. Per-camera zone memory
Each camera index stores its own active zone and preset zones independently. Switching cameras automatically restores the correct zone for that camera. Users never lose their zone configuration when switching sources.

### 6. Stateless API, stateful pipeline
API endpoints are fully stateless — no sessions, no cookies. The camera pipeline runs as a background thread maintaining shared state via `camera_state`. This separation keeps the API clean and testable while the pipeline handles real-time processing.

### 7. Preprocessing before detection
CLAHE enhancement is applied before YOLO inference to improve detection accuracy in low-light or low-contrast scenes. This is especially important for outdoor camera setups where lighting varies throughout the day.
