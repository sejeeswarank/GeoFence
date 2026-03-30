"""
Main FastAPI application for GeoFence Vision.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from alerts import AlertManager
from auth_service import get_current_user, get_firebase_web_config
from config import (
    CAMERA_INDEX,
    CAMERA_SCAN_LIMIT,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    INDEX_HTML,
    LOGIN_HTML,
    PREPROCESSING_ENABLED,
    REGISTER_HTML,
    STREAM_JPEG_QUALITY,
    TRACKING_ENABLED,
)
from detector import ObjectDetector
from drive_storage import DriveConfigurationError, DriveStorage
from geofence import GeoFence
from preprocessing import preprocess_frame
from tracker import ObjectTracker


app = FastAPI(
    title="GeoFence Vision API",
    description="Real-time geofencing with Firebase auth and Google Drive sync.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


detector: Optional[ObjectDetector] = None
geofence = GeoFence()
tracker = ObjectTracker()
alert_manager = AlertManager()
drive_storage = DriveStorage()

camera_state = {
    "running": False,
    "selected_camera_index": CAMERA_INDEX,
    "frame_b64": None,
    "fps": 0.0,
    "detections": [],
    "thread": None,
    "last_error": None,
}


class ZoneConfig(BaseModel):
    points: list[list[int]]
    name: Optional[str] = "Zone A"


class CameraControl(BaseModel):
    action: str


class CameraSelection(BaseModel):
    camera_index: int


class SnapshotRequest(BaseModel):
    profile: Optional[dict] = None


def get_detector() -> ObjectDetector:
    global detector
    if detector is None:
        detector = ObjectDetector()
    return detector


def read_html(path: Path) -> str:
    if not path.exists():
        raise HTTPException(500, f"HTML file not found at {path}")
    return path.read_text(encoding="utf-8")


def build_capture(camera_index: int) -> cv2.VideoCapture:
    if os.name == "nt":
        return cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(camera_index)


def configure_capture(capture: cv2.VideoCapture) -> None:
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)


def stop_camera_thread(wait_timeout: float = 3.0) -> None:
    camera_state["running"] = False
    thread = camera_state.get("thread")
    if thread and thread.is_alive():
        thread.join(wait_timeout)
    camera_state["thread"] = None


def start_camera_thread() -> dict:
    if camera_state["running"]:
        return {"status": "already running"}

    tracker.reset()
    camera_state["frame_b64"] = None
    camera_state["fps"] = 0.0
    camera_state["detections"] = []
    camera_state["last_error"] = None
    camera_state["running"] = True
    thread = threading.Thread(target=camera_loop, daemon=True)
    thread.start()
    camera_state["thread"] = thread
    return {"status": "started"}


def enumerate_cameras(limit: int = CAMERA_SCAN_LIMIT) -> list[dict]:
    cameras: list[dict] = []

    for index in range(limit):
        capture = build_capture(index)
        configure_capture(capture)
        available = False
        if capture.isOpened():
            ok, _ = capture.read()
            available = bool(ok)
        capture.release()

        if available:
            cameras.append(
                {
                    "index": index,
                    "label": f"Camera {index}",
                    "selected": index == camera_state["selected_camera_index"],
                }
            )

    return cameras


def annotate_detection(frame, detection: dict, zone_active: bool) -> None:
    x1, y1, x2, y2 = detection["bbox"]
    status = detection["zone_status"]
    object_id = detection.get("object_id", "?")

    if not zone_active or status == "no-zone":
        color = (255, 180, 0)
        status_text = "NO ZONE"
    elif status == "alert":
        color = (0, 110, 255)
        status_text = "ALERT"
    else:
        color = (0, 220, 120)
        status_text = "SAFE"

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = (
        f"#{object_id} {detection['label']} "
        f"{detection['confidence']:.0%} {status_text}"
    )
    cv2.putText(
        frame,
        label,
        (x1, max(20, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        color,
        2,
    )


def encode_frame(frame) -> str:
    success, buffer = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY],
    )
    if not success:
        raise RuntimeError("Failed to encode frame")
    return base64.b64encode(buffer).decode("utf-8")


def process_camera_frame(frame, pipeline_detector, previous_time: float) -> float:
    processed_frame = preprocess_frame(frame)
    detections = pipeline_detector.detect(processed_frame)
    detections = tracker.update(detections)

    zone_active = geofence.is_active()
    annotated = geofence.draw_zone(frame.copy())

    for detection in detections:
        center_x, center_y = detection["center"]
        inside_zone = zone_active and geofence.is_inside(center_x, center_y)
        detection["inside_zone"] = inside_zone
        detection["zone_status"] = "safe" if inside_zone else ("alert" if zone_active else "no-zone")
        detection["zone_name"] = geofence.name if zone_active else None
        annotate_detection(annotated, detection, zone_active)

    alert_manager.process(detections, geofence.name if zone_active else None)

    current_time = time.time()
    fps = 1 / max(current_time - previous_time, 1e-6)
    cv2.putText(
        annotated,
        f"FPS: {fps:.1f}",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 0),
        2,
    )

    camera_state["frame_b64"] = encode_frame(annotated)
    camera_state["fps"] = round(fps, 1)
    camera_state["detections"] = detections
    return current_time


def camera_loop() -> None:
    capture = build_capture(camera_state["selected_camera_index"])
    configure_capture(capture)

    if not capture.isOpened():
        camera_state["last_error"] = f"Unable to open camera {camera_state['selected_camera_index']}."
        camera_state["running"] = False
        capture.release()
        return

    try:
        pipeline_detector = get_detector()
        previous_time = time.time()
        camera_state["last_error"] = None

        while camera_state["running"]:
            ok, frame = capture.read()
            if not ok:
                camera_state["last_error"] = "Camera frame capture failed."
                break

            previous_time = process_camera_frame(frame, pipeline_detector, previous_time)
    except Exception as exc:  # pragma: no cover
        camera_state["last_error"] = str(exc)
    finally:
        capture.release()
        camera_state["running"] = False


def build_snapshot_payload(user: dict, profile: Optional[dict]) -> dict:
    return {
        "uid": user["uid"],
        "email": user.get("email"),
        "name": user.get("name"),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "zone": geofence.get_config(),
        "alerts": alert_manager.get_recent(100),
        "camera": {
            "selected_camera_index": camera_state["selected_camera_index"],
            "preprocessing_enabled": PREPROCESSING_ENABLED,
            "tracking_enabled": TRACKING_ENABLED,
        },
        "profile": profile or {},
    }


def apply_snapshot(snapshot: dict) -> None:
    zone = snapshot.get("zone") or {}
    points = zone.get("points") or []
    if zone.get("active") and len(points) >= 3:
        geofence.set_zone(points, zone.get("name") or "Zone A")
    else:
        geofence.clear()

    camera = snapshot.get("camera") or {}
    selected_index = camera.get("selected_camera_index")
    if isinstance(selected_index, int):
        camera_state["selected_camera_index"] = selected_index


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse, tags=["UI"])
async def serve_login() -> str:
    return read_html(LOGIN_HTML)


@app.get("/register", response_class=HTMLResponse, tags=["UI"])
async def serve_register() -> str:
    return read_html(REGISTER_HTML)


@app.get("/app", response_class=HTMLResponse, tags=["UI"])
async def serve_app() -> str:
    return read_html(INDEX_HTML)


@app.get("/auth/firebase-config", tags=["Auth"])
async def firebase_config() -> dict:
    return get_firebase_web_config()


@app.get("/auth/session", tags=["Auth"])
async def auth_session(current_user: dict = Depends(get_current_user)) -> dict:
    return {
        "user": current_user,
        "drive": drive_storage.status(),
    }


@app.post("/camera/control", tags=["Camera"], responses={400: {"description": "Invalid camera action payload"}})
async def control_camera(body: CameraControl) -> dict:
    action = body.action.lower()

    if action == "start":
        return start_camera_thread()

    if action == "stop":
        stop_camera_thread()
        return {"status": "stopped"}

    raise HTTPException(400, "action must be 'start' or 'stop'")


@app.get("/camera/options", tags=["Camera"])
async def get_camera_options() -> dict:
    return {
        "selected_camera_index": camera_state["selected_camera_index"],
        "cameras": enumerate_cameras(),
    }


@app.post("/camera/select", tags=["Camera"], responses={400: {"description": "Requested camera index is invalid or unavailable"}})
async def select_camera(body: CameraSelection) -> dict:
    available_indexes = {camera["index"] for camera in enumerate_cameras()}
    if body.camera_index not in available_indexes:
        raise HTTPException(400, f"Camera {body.camera_index} is not available")

    was_running = camera_state["running"]
    if was_running:
        stop_camera_thread()

    camera_state["selected_camera_index"] = body.camera_index
    camera_state["frame_b64"] = None
    camera_state["fps"] = 0.0
    camera_state["detections"] = []
    camera_state["last_error"] = None

    response = {
        "status": "selected",
        "selected_camera_index": camera_state["selected_camera_index"],
        "restarted": False,
    }

    if was_running:
        start_camera_thread()
        response["restarted"] = True

    return response


@app.get("/camera/frame", tags=["Camera"])
async def get_frame() -> dict:
    if not camera_state["frame_b64"]:
        return {"frame": None, "fps": 0, "detections": []}

    return {
        "frame": camera_state["frame_b64"],
        "fps": camera_state["fps"],
        "detections": camera_state["detections"],
    }


@app.get("/zone", tags=["Geo Fence"])
async def get_zone() -> dict:
    return geofence.get_config()


@app.post("/zone", tags=["Geo Fence"], responses={400: {"description": "Insufficient points provided to create polygon zone"}})
async def set_zone(config: ZoneConfig) -> dict:
    if len(config.points) < 3:
        raise HTTPException(400, "Zone needs at least 3 points")
    geofence.set_zone(config.points, config.name or "Zone A")
    return {"status": "zone updated", "zone": geofence.get_config()}


@app.delete("/zone", tags=["Geo Fence"])
async def clear_zone() -> dict:
    geofence.clear()
    return {"status": "zone cleared"}


@app.get("/alerts", tags=["Alerts"])
async def get_alerts(limit: int = 50) -> dict:
    return {"alerts": alert_manager.get_recent(limit)}


@app.delete("/alerts", tags=["Alerts"])
async def clear_alerts() -> dict:
    alert_manager.clear()
    return {"status": "alerts cleared"}


@app.post("/storage/snapshot", tags=["Storage"])
async def save_snapshot(body: SnapshotRequest, current_user: dict = Depends(get_current_user)) -> dict:
    try:
        snapshot = build_snapshot_payload(current_user, body.profile)
        result = drive_storage.save_user_snapshot(current_user["uid"], snapshot)
        return {
            "status": "saved",
            "snapshot": snapshot,
            "file": result,
        }
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/storage/snapshot", tags=["Storage"])
async def get_snapshot(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        snapshot = drive_storage.load_user_snapshot(current_user["uid"])
        return {
            "status": "loaded" if snapshot else "empty",
            "snapshot": snapshot,
        }
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/storage/restore", tags=["Storage"])
async def restore_snapshot(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        snapshot = drive_storage.load_user_snapshot(current_user["uid"])
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not snapshot:
        return {"status": "empty", "snapshot": None}

    apply_snapshot(snapshot)
    return {"status": "restored", "snapshot": snapshot, "zone": geofence.get_config()}


@app.get("/status", tags=["System"])
async def get_status() -> dict:
    return {
        "camera_running": camera_state["running"],
        "selected_camera_index": camera_state["selected_camera_index"],
        "fps": camera_state["fps"],
        "zone_active": geofence.is_active(),
        "zone_name": geofence.name,
        "total_alerts": alert_manager.total_count(),
        "active_detections": len(camera_state["detections"]),
        "tracking_enabled": TRACKING_ENABLED,
        "preprocessing_enabled": PREPROCESSING_ENABLED,
        "last_error": camera_state["last_error"],
    }
