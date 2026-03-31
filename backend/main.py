"""
Main FastAPI application for GeoFence Vision.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from datetime import datetime
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import cv2
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from alerts import AlertManager
from auth_service import get_current_user, get_firebase_web_config, verify_firebase_token
from config import (
    CAMERA_INDEX,
    CAMERA_SCAN_LIMIT,
    DASHBOARD_JS,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    INDEX_HTML,
    LOGIN_HTML,
    LOGO_PNG,
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


RTSP_CAPTURE_OPTIONS = "rtsp_transport;tcp|stimeout;10000000"


detector: Optional[ObjectDetector] = None
drive_storage = DriveStorage()
pending_drive_oauth: dict[str, str] = {}
user_sessions: dict[str, dict] = {}
session_lock = threading.Lock()


class ZoneConfig(BaseModel):
    points: list[list[int]]
    name: Optional[str] = "Zone A"


class CameraControl(BaseModel):
    action: str
    source_type: Optional[str] = None
    source_url: Optional[str] = None


class CameraSelection(BaseModel):
    camera_index: int


class CameraSourceRequest(BaseModel):
    source_type: str
    source_url: Optional[str] = None


class SnapshotRequest(BaseModel):
    profile: Optional[dict] = None
    saved_cameras: Optional[list[dict]] = None
    last_selected_camera_id: Optional[str] = None


class CameraStorageRequest(BaseModel):
    saved_cameras: list[dict] = Field(default_factory=list)
    last_selected_camera_id: Optional[str] = ""
    profile: Optional[dict] = None


class SavedZoneRequest(BaseModel):
    name: str
    points: list[list[int]]
    camera_index: Optional[int] = None


def create_camera_state() -> dict:
    return {
        "running": False,
        "selected_camera_index": CAMERA_INDEX,
        "source_type": "local",
        "source_url": None,
        "frame_b64": None,
        "fps": 0.0,
        "detections": [],
        "thread": None,
        "last_error": None,
    }


def create_user_session() -> dict:
    return {
        "geofence": GeoFence(),
        "tracker": ObjectTracker(),
        "alert_manager": AlertManager(),
        "camera_state": create_camera_state(),
        "saved_zones_by_camera": {},
        "active_zone_by_camera": {},
    }


def get_user_session(uid: str) -> dict:
    with session_lock:
        session = user_sessions.get(uid)
        if session is None:
            session = create_user_session()
            user_sessions[uid] = session
        return session


def normalize_points(points: list[list[int]]) -> list[list[int]]:
    return [[int(point[0]), int(point[1])] for point in points]


def upsert_saved_zone(session: dict, camera_index: int, name: str, points: list[list[int]]) -> dict:
    normalized_points = normalize_points(points)
    saved_zones_by_camera = session["saved_zones_by_camera"]
    zones = saved_zones_by_camera.setdefault(camera_index, [])

    for zone in zones:
        if zone["name"].strip().lower() == name.strip().lower():
            zone["name"] = name
            zone["points"] = normalized_points
            return zone

    zone = {"name": name, "points": normalized_points}
    zones.append(zone)
    zones.sort(key=lambda item: item["name"].lower())
    return zone


def get_saved_zones(session: dict, camera_index: int) -> list[dict]:
    zones = session["saved_zones_by_camera"].get(camera_index, [])
    return [{"name": zone["name"], "points": zone["points"]} for zone in zones]


def delete_saved_zone(session: dict, camera_index: int, name: str) -> bool:
    saved_zones_by_camera = session["saved_zones_by_camera"]
    zones = saved_zones_by_camera.get(camera_index, [])
    remaining = [
        zone
        for zone in zones
        if zone["name"].strip().lower() != name.strip().lower()
    ]
    if len(remaining) == len(zones):
        return False
    if remaining:
        saved_zones_by_camera[camera_index] = remaining
    else:
        saved_zones_by_camera.pop(camera_index, None)
    return True


def set_active_zone_for_camera(session: dict, camera_index: int, name: str, points: list[list[int]]) -> dict:
    zone = {"name": name, "points": normalize_points(points)}
    session["active_zone_by_camera"][camera_index] = zone
    return zone


def get_active_zone_for_camera(session: dict, camera_index: int) -> Optional[dict]:
    zone = session["active_zone_by_camera"].get(camera_index)
    if not zone:
        return None
    return {"name": zone["name"], "points": zone["points"]}


def apply_camera_zone(session: dict, camera_index: int) -> None:
    geofence = session["geofence"]
    zone = get_active_zone_for_camera(session, camera_index)
    if zone and len(zone["points"]) >= 3:
        geofence.set_zone(zone["points"], zone["name"])
    else:
        geofence.clear()

def get_detector() -> ObjectDetector:
    global detector
    if detector is None:
        detector = ObjectDetector()
    return detector


def read_html(path: Path) -> str:
    if not path.exists():
        raise HTTPException(500, f"HTML file not found at {path}")
    return path.read_text(encoding="utf-8")


def read_text_file(path: Path) -> str:
    if not path.exists():
        raise HTTPException(500, f"Asset file not found at {path}")
    return path.read_text(encoding="utf-8")


def normalize_source_url(source_type: str, source_url: Optional[str]) -> Optional[str]:
    if source_url is None:
        return None

    trimmed = source_url.strip()
    if not trimmed:
        return None

    if source_type != "mobile":
        return trimmed

    candidate = trimmed if "://" in trimmed else f"http://{trimmed}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return trimmed

    if not parsed.path or parsed.path == "/":
        parsed = parsed._replace(path="/video")

    return urlunparse(parsed)


def is_rtsp_url(source: str) -> bool:
    return source.lower().startswith("rtsp://")


def build_capture(session: dict, source=None) -> cv2.VideoCapture:
    camera_state = session["camera_state"]
    if source is None:
        source = camera_state["selected_camera_index"]
    if isinstance(source, str):
        if is_rtsp_url(source):
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = RTSP_CAPTURE_OPTIONS
            capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10_000)
            if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10_000)
            return capture
        return cv2.VideoCapture(source)
    if os.name == "nt":
        return cv2.VideoCapture(source, cv2.CAP_DSHOW)
    return cv2.VideoCapture(source)


def configure_capture(capture: cv2.VideoCapture) -> None:
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)


def resolve_camera_source(session: dict) -> tuple[str, int | str]:
    camera_state = session["camera_state"]
    source_type = camera_state.get("source_type", "local")
    if source_type in ("ip", "mobile") and camera_state.get("source_url"):
        return source_type, camera_state["source_url"]
    return "local", camera_state["selected_camera_index"]

def set_source_open_error(session: dict, source_type: str, source: int | str) -> None:
    camera_state = session["camera_state"]
    if source_type == "ip" and isinstance(source, str) and is_rtsp_url(source):
        camera_state["last_error"] = (
            "Unable to open the RTSP stream. Check the camera URL, network access, "
            "and whether RTSP over TCP is allowed from this PC."
        )
    else:
        label = source if isinstance(source, str) else f"camera {source}"
        camera_state["last_error"] = f"Unable to open {label}."


def set_source_read_error(session: dict, source: int | str) -> None:
    camera_state = session["camera_state"]
    if isinstance(source, str):
        camera_state["last_error"] = (
            "Connected to the selected source, but no frames were received."
        )
    else:
        camera_state["last_error"] = "Camera frame capture failed."


def stop_camera_thread(session: dict, wait_timeout: float = 3.0) -> None:
    camera_state = session["camera_state"]
    camera_state["running"] = False
    thread = camera_state.get("thread")
    if thread and thread.is_alive():
        thread.join(wait_timeout)
    camera_state["thread"] = None


def start_camera_thread(uid: str, session: dict) -> dict:
    camera_state = session["camera_state"]
    tracker = session["tracker"]
    if camera_state["running"]:
        return {"status": "already running"}

    tracker.reset()
    camera_state["frame_b64"] = None
    camera_state["fps"] = 0.0
    camera_state["detections"] = []
    camera_state["last_error"] = None
    camera_state["running"] = True
    thread = threading.Thread(target=camera_loop, args=(uid,), daemon=True)
    thread.start()
    camera_state["thread"] = thread
    return {"status": "started"}

def enumerate_cameras(session: dict, limit: int = CAMERA_SCAN_LIMIT) -> list[dict]:
    cameras: list[dict] = []
    camera_state = session["camera_state"]

    for index in range(limit):
        capture = build_capture(session, index)
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


def process_camera_frame(session: dict, frame, pipeline_detector, previous_time: float) -> float:
    tracker = session["tracker"]
    geofence = session["geofence"]
    alert_manager = session["alert_manager"]
    camera_state = session["camera_state"]

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

def analyze_video_frame(
    frame,
    pipeline_detector: ObjectDetector,
    video_tracker: ObjectTracker,
    video_geofence: GeoFence,
    video_alerts: AlertManager,
) -> tuple:
    processed_frame = preprocess_frame(frame)
    detections = video_tracker.update(pipeline_detector.detect(processed_frame))

    zone_active = video_geofence.is_active()
    annotated = video_geofence.draw_zone(frame.copy())

    for detection in detections:
        center_x, center_y = detection["center"]
        inside_zone = zone_active and video_geofence.is_inside(center_x, center_y)
        detection["inside_zone"] = inside_zone
        detection["zone_status"] = "safe" if inside_zone else ("alert" if zone_active else "no-zone")
        detection["zone_name"] = video_geofence.name if zone_active else None
        annotate_detection(annotated, detection, zone_active)

    video_alerts.process(detections, video_geofence.name if zone_active else None)
    return annotated, detections


def analyze_uploaded_video(
    video_path: Path,
    zone_name: Optional[str] = None,
    zone_points: Optional[list[list[int]]] = None,
) -> dict:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise HTTPException(400, "Unable to open the uploaded video.")

    detector_instance = get_detector()
    video_tracker = ObjectTracker()
    video_tracker.reset()
    video_alerts = AlertManager()
    video_geofence = GeoFence()
    video_geofence.clear()

    normalized_points = normalize_points(zone_points or []) if zone_points else []
    if len(normalized_points) >= 3:
        video_geofence.set_zone(normalized_points, zone_name or "Uploaded Video Zone")

    total_frames = 0
    processed_frames = 0
    label_counts: dict[str, int] = {}
    last_detections: list[dict] = []
    last_frame_b64: Optional[str] = None
    started_at = time.time()
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 0.0

    # Analyze ~3 frames per second instead of every frame
    target_analysis_fps = 3
    skip_interval = max(1, int(source_fps / target_analysis_fps)) if source_fps > 0 else 1

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            total_frames += 1

            # Skip frames that aren't on the analysis interval
            if total_frames % skip_interval != 0:
                continue

            annotated, detections = analyze_video_frame(
                frame,
                detector_instance,
                video_tracker,
                video_geofence,
                video_alerts,
            )
            processed_frames += 1
            last_detections = detections
            last_frame_b64 = encode_frame(annotated)

            for detection in detections:
                label_counts[detection["label"]] = label_counts.get(detection["label"], 0) + 1
    finally:
        capture.release()

    duration_seconds = max(time.time() - started_at, 1e-6)
    video_duration = 0.0
    if source_fps and total_frames:
        video_duration = total_frames / source_fps

    return {
        "status": "processed",
        "summary": {
            "frames_total": total_frames,
            "frames_processed": processed_frames,
            "video_seconds": round(video_duration, 2),
            "processing_seconds": round(duration_seconds, 2),
            "detections_total": sum(label_counts.values()),
            "alert_events": len(video_alerts.get_recent(200)),
            "zone_name": video_geofence.name if video_geofence.is_active() else "",
        },
        "label_counts": label_counts,
        "alerts": video_alerts.get_recent(50),
        "last_detections": last_detections,
        "preview_frame": last_frame_b64,
    }


def camera_loop(uid: str) -> None:
    session = get_user_session(uid)
    camera_state = session["camera_state"]
    tracker = session["tracker"]
    capture: Optional[cv2.VideoCapture] = None
    active_source_type: Optional[str] = None
    active_source: Optional[int | str] = None
    try:
        pipeline_detector = get_detector()
        previous_time = time.time()
        camera_state["last_error"] = None

        while camera_state["running"]:
            desired_source_type, desired_source = resolve_camera_source(session)
            desired_signature = (desired_source_type, str(desired_source))
            active_signature = (
                None
                if active_source is None or active_source_type is None
                else (active_source_type, str(active_source))
            )

            if capture is None:
                capture = build_capture(session, desired_source)
                configure_capture(capture)
                if not capture.isOpened():
                    set_source_open_error(session, desired_source_type, desired_source)
                    capture.release()
                    capture = None
                    time.sleep(0.35)
                    continue

                active_source_type = desired_source_type
                active_source = desired_source
                tracker.reset()
                camera_state["frame_b64"] = None
                camera_state["fps"] = 0.0
                camera_state["detections"] = []
                camera_state["last_error"] = None
                previous_time = time.time()

            elif desired_signature != active_signature:
                next_capture = build_capture(session, desired_source)
                configure_capture(next_capture)
                if not next_capture.isOpened():
                    set_source_open_error(session, desired_source_type, desired_source)
                    next_capture.release()
                else:
                    capture.release()
                    capture = next_capture
                    active_source_type = desired_source_type
                    active_source = desired_source
                    tracker.reset()
                    camera_state["frame_b64"] = None
                    camera_state["fps"] = 0.0
                    camera_state["detections"] = []
                    camera_state["last_error"] = None
                    previous_time = time.time()
                    continue

            ok, frame = capture.read()
            if not ok:
                set_source_read_error(session, active_source if active_source is not None else desired_source)
                capture.release()
                capture = None
                active_source_type = None
                active_source = None
                time.sleep(0.2)
                continue

            previous_time = process_camera_frame(session, frame, pipeline_detector, previous_time)
    except Exception as exc:  # pragma: no cover
        camera_state["last_error"] = str(exc)
    finally:
        if capture is not None:
            capture.release()
        camera_state["running"] = False
        camera_state["thread"] = None

def build_user_record(user: dict) -> dict:
    return {
        "uid": user["uid"],
        "email": user.get("email"),
        "name": user.get("name"),
        "email_verified": bool(user.get("email_verified", False)),
    }


def normalize_saved_camera_config(camera: dict, position: int = 0) -> Optional[dict]:
    if not isinstance(camera, dict):
        return None

    raw_points = (
        camera.get("polygon_points")
        or camera.get("polygonPoints")
        or camera.get("points")
        or []
    )
    try:
        polygon_points = normalize_points(raw_points)
    except (TypeError, ValueError, IndexError):
        polygon_points = []

    return {
        "id": str(camera.get("id") or f"camera-{position + 1}"),
        "camera_name": str(camera.get("camera_name") or camera.get("name") or "").strip() or f"Camera {position + 1}",
        "camera_url": str(camera.get("camera_url") or camera.get("url") or "").strip(),
        "zone_name": str(camera.get("zone_name") or camera.get("zoneName") or "").strip() or "Zone A",
        "polygon_points": polygon_points,
        "source_type": str(camera.get("source_type") or "").strip(),
    }


def normalize_saved_camera_configs(cameras: Optional[list[dict]]) -> list[dict]:
    if not isinstance(cameras, list):
        return []

    normalized: list[dict] = []
    for position, camera in enumerate(cameras):
        normalized_camera = normalize_saved_camera_config(camera, position)
        if normalized_camera:
            normalized.append(normalized_camera)

    normalized.sort(key=lambda item: item["camera_name"].lower())
    return normalized


def extract_storage_payload(snapshot: Optional[dict]) -> dict:
    if not isinstance(snapshot, dict):
        return {
            "saved_cameras": [],
            "last_selected_camera_id": "",
            "profile": {},
            "user_details": {},
            "saved_at": None,
        }

    profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
    user_details = snapshot.get("user") if isinstance(snapshot.get("user"), dict) else {}
    return {
        "saved_cameras": normalize_saved_camera_configs(snapshot.get("saved_cameras") or []),
        "last_selected_camera_id": str(snapshot.get("last_selected_camera_id") or ""),
        "profile": profile,
        "user_details": user_details,
        "saved_at": snapshot.get("saved_at"),
    }


def build_snapshot_payload(
    session: dict,
    user: dict,
    profile: Optional[dict],
    saved_cameras: Optional[list[dict]] = None,
    last_selected_camera_id: Optional[str] = None,
    existing_snapshot: Optional[dict] = None,
) -> dict:
    existing_snapshot = existing_snapshot if isinstance(existing_snapshot, dict) else {}
    user_record = build_user_record(user)
    geofence = session["geofence"]
    alert_manager = session["alert_manager"]
    camera_state = session["camera_state"]
    saved_zones_by_camera = session["saved_zones_by_camera"]
    active_zone_by_camera = session["active_zone_by_camera"]

    merged_profile: dict = {}
    if isinstance(existing_snapshot.get("profile"), dict):
        merged_profile.update(existing_snapshot["profile"])
    if isinstance(profile, dict):
        merged_profile.update(profile)
    merged_profile.setdefault("displayName", user_record.get("name") or "")
    merged_profile.setdefault("email", user_record.get("email") or "")
    merged_profile["uid"] = user_record["uid"]
    merged_profile["email_verified"] = user_record["email_verified"]

    normalized_saved_cameras = normalize_saved_camera_configs(
        saved_cameras if saved_cameras is not None else existing_snapshot.get("saved_cameras")
    )
    resolved_last_selected_camera_id = (
        str(last_selected_camera_id)
        if last_selected_camera_id is not None
        else str(existing_snapshot.get("last_selected_camera_id") or "")
    )

    return {
        "uid": user_record["uid"],
        "email": user_record.get("email"),
        "name": user_record.get("name"),
        "user": user_record,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "zone": geofence.get_config(),
        "alerts": alert_manager.get_recent(100),
        "camera": {
            "selected_camera_index": camera_state["selected_camera_index"],
            "available_cameras": enumerate_cameras(session),
            "preprocessing_enabled": PREPROCESSING_ENABLED,
            "tracking_enabled": TRACKING_ENABLED,
            "source_type": camera_state.get("source_type"),
            "source_url": camera_state.get("source_url"),
        },
        "saved_zones_by_camera": {
            str(camera_index): zones
            for camera_index, zones in saved_zones_by_camera.items()
        },
        "active_zone_by_camera": {
            str(camera_index): zone
            for camera_index, zone in active_zone_by_camera.items()
            if zone
        },
        "profile": merged_profile,
        "saved_cameras": normalized_saved_cameras,
        "last_selected_camera_id": resolved_last_selected_camera_id,
    }


def apply_snapshot(session: dict, snapshot: dict) -> None:
    saved_zones_by_camera = session["saved_zones_by_camera"]
    active_zone_by_camera = session["active_zone_by_camera"]
    camera_state = session["camera_state"]
    alert_manager = session["alert_manager"]
    tracker = session["tracker"]

    saved_zones_by_camera.clear()
    active_zone_by_camera.clear()
    saved_zone_map = snapshot.get("saved_zones_by_camera") or {}
    for camera_index, zones in saved_zone_map.items():
        try:
            numeric_index = int(camera_index)
        except (TypeError, ValueError):
            continue
        if isinstance(zones, list):
            saved_zones_by_camera[numeric_index] = [
                {
                    "name": zone.get("name", f"Zone {position + 1}"),
                    "points": normalize_points(zone.get("points", [])),
                }
                for position, zone in enumerate(zones)
                if isinstance(zone, dict) and len(zone.get("points", [])) >= 3
            ]

    active_zone_map = snapshot.get("active_zone_by_camera") or {}
    for camera_index, zone in active_zone_map.items():
        try:
            numeric_index = int(camera_index)
        except (TypeError, ValueError):
            continue
        if isinstance(zone, dict) and len(zone.get("points", [])) >= 3:
            active_zone_by_camera[numeric_index] = {
                "name": zone.get("name", "Zone A"),
                "points": normalize_points(zone.get("points", [])),
            }

    camera = snapshot.get("camera") or {}
    selected_index = camera.get("selected_camera_index")
    if isinstance(selected_index, int):
        camera_state["selected_camera_index"] = selected_index

    source_type = str(camera.get("source_type") or camera_state.get("source_type") or "local")
    camera_state["source_type"] = source_type
    camera_state["source_url"] = normalize_source_url(source_type, camera.get("source_url"))
    camera_state["frame_b64"] = None
    camera_state["fps"] = 0.0
    camera_state["detections"] = []
    camera_state["last_error"] = None
    tracker.reset()

    fallback_zone = snapshot.get("zone") or {}
    fallback_points = fallback_zone.get("points") or []
    if (
        camera_state["selected_camera_index"] not in active_zone_by_camera
        and fallback_zone.get("active")
        and len(fallback_points) >= 3
    ):
        active_zone_by_camera[camera_state["selected_camera_index"]] = {
            "name": fallback_zone.get("name") or "Zone A",
            "points": normalize_points(fallback_points),
        }

    apply_camera_zone(session, camera_state["selected_camera_index"])

    saved_alerts = snapshot.get("alerts")
    alert_manager.clear()
    if saved_alerts and isinstance(saved_alerts, list):
        for alert in reversed(saved_alerts):
            alert_manager._alerts.appendleft(alert)
        alert_manager._total = len(saved_alerts)

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


@app.get("/dashboard.js", tags=["UI"])
async def serve_dashboard_script() -> Response:
    return Response(
        content=read_text_file(Path(DASHBOARD_JS)),
        media_type="text/javascript",
    )


@app.get("/logo.png", tags=["UI"])
async def serve_logo():
    from fastapi.responses import FileResponse
    return FileResponse(LOGO_PNG, media_type="image/png")


@app.get("/auth/firebase-config", tags=["Auth"])
async def firebase_config() -> dict:
    return get_firebase_web_config()


@app.get("/auth/session", tags=["Auth"])
async def auth_session(current_user: dict = Depends(get_current_user)) -> dict:
    storage = {"status": "unconfigured", **extract_storage_payload(None), "snapshot": None}

    try:
        drive = drive_storage.status(current_user["uid"])
        if drive["configured"]:
            snapshot = drive_storage.load_user_snapshot(current_user["uid"])
            storage = {
                "status": "loaded" if snapshot else "empty",
                "snapshot": snapshot,
                **extract_storage_payload(snapshot),
            }
    except DriveConfigurationError as exc:
        drive = {
            "configured": False,
            "has_credentials": True,
            "credentials_file": "",
            "token_file": "",
            "token_directory": "",
            "legacy_token_detected": False,
            "message": str(exc),
        }
    except Exception as exc:
        drive = {
            "configured": False,
            "has_credentials": False,
            "credentials_file": "",
            "token_file": "",
            "token_directory": "",
            "legacy_token_detected": False,
            "message": f"Unable to check Google Drive right now: {exc}",
        }

    return {
        "user": current_user,
        "drive": drive,
        "storage": storage,
    }


@app.get("/auth/drive/connect", tags=["Auth"])
async def drive_connect(request: Request, token: str = ""):
    """Redirect the user to Google's OAuth consent screen."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing Firebase token.")

    try:
        decoded = verify_firebase_token(token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    current_user = build_user_record(
        {
            "uid": decoded["uid"],
            "email": decoded.get("email"),
            "name": decoded.get("name"),
            "email_verified": decoded.get("email_verified", False),
        }
    )
    redirect_uri = str(request.url_for("drive_callback"))
    try:
        auth_url, code_verifier = drive_storage.build_auth_url(redirect_uri, state=current_user["uid"])
        pending_drive_oauth[current_user["uid"]] = code_verifier
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url=auth_url)


@app.get("/auth/drive/callback", tags=["Auth"])
async def drive_callback(request: Request, code: str = "", state: str = ""):
    """Handle the OAuth callback, exchange the code for tokens, then redirect back."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    if not state.strip():
        raise HTTPException(status_code=400, detail="Missing user state for Drive callback.")

    uid = state.strip()
    code_verifier = pending_drive_oauth.pop(uid, "")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Drive sign-in session expired. Please click Connect to Drive again.")

    redirect_uri = str(request.url_for("drive_callback"))
    try:
        drive_storage.exchange_code(code, redirect_uri, uid, code_verifier)
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url="/app")


@app.post("/camera/control", tags=["Camera"], responses={400: {"description": "Invalid camera action payload"}})
async def control_camera(body: CameraControl, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    action = body.action.lower()

    if action == "start":
        resolved_source_type = body.source_type or camera_state["source_type"]
        camera_state["source_type"] = resolved_source_type
        camera_state["source_url"] = normalize_source_url(
            resolved_source_type,
            body.source_url,
        )
        return start_camera_thread(current_user["uid"], session)

    if action == "stop":
        stop_camera_thread(session)
        return {"status": "stopped"}

    raise HTTPException(400, "action must be 'start' or 'stop'")


@app.post("/camera/set-source", tags=["Camera"])
async def set_camera_source(body: CameraSourceRequest, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    camera_state["source_type"] = body.source_type
    camera_state["source_url"] = normalize_source_url(
        body.source_type,
        body.source_url,
    )
    return {
        "status": "ok",
        "source_type": body.source_type,
        "source_url": camera_state["source_url"],
    }


@app.get("/camera/options", tags=["Camera"])
async def get_camera_options(current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    return {
        "selected_camera_index": camera_state["selected_camera_index"],
        "cameras": enumerate_cameras(session),
    }


@app.post("/camera/select", tags=["Camera"], responses={400: {"description": "Requested camera index is invalid or unavailable"}})
async def select_camera(body: CameraSelection, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    available_indexes = {camera["index"] for camera in enumerate_cameras(session)}
    if body.camera_index not in available_indexes:
        raise HTTPException(400, f"Camera {body.camera_index} is not available")

    was_running = camera_state["running"]
    camera_state["source_type"] = "local"
    camera_state["source_url"] = None
    camera_state["selected_camera_index"] = body.camera_index
    camera_state["frame_b64"] = None
    camera_state["fps"] = 0.0
    camera_state["detections"] = []
    camera_state["last_error"] = None
    apply_camera_zone(session, camera_state["selected_camera_index"])

    response = {
        "status": "selected",
        "selected_camera_index": camera_state["selected_camera_index"],
        "switched_while_running": was_running,
    }

    if not was_running:
        response["status"] = "ready"

    return response


@app.get("/camera/frame", tags=["Camera"])
async def get_frame(current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    if not camera_state["frame_b64"]:
        return {"frame": None, "fps": 0, "detections": []}

    return {
        "frame": camera_state["frame_b64"],
        "fps": camera_state["fps"],
        "detections": camera_state["detections"],
    }

@app.post("/video/analyze", tags=["Video"])
async def analyze_video_upload(
    file: UploadFile = File(...),
    zone_name: Optional[str] = Form(None),
    zone_points: Optional[str] = Form(None),
) -> dict:
    if not file.filename:
        raise HTTPException(400, "Choose a video file to upload.")

    suffix = Path(file.filename).suffix or ".mp4"
    parsed_points: list[list[int]] = []
    if zone_points:
        try:
            parsed_points = normalize_points(json.loads(zone_points)) or []
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "Zone points must be valid JSON.") from exc

    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := await file.read(1024 * 1024):
                temp_file.write(chunk)

        result = analyze_uploaded_video(
            temp_path,
            zone_name=zone_name,
            zone_points=parsed_points,
        )
        result["filename"] = file.filename
        return result
    finally:
        await file.close()
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.get("/zone", tags=["Geo Fence"])
async def get_zone(current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    return session["geofence"].get_config()


@app.post("/zone", tags=["Geo Fence"], responses={400: {"description": "Insufficient points provided to create polygon zone"}})
async def set_zone(config: ZoneConfig, current_user: dict = Depends(get_current_user)) -> dict:
    if len(config.points) < 3:
        raise HTTPException(400, "Zone needs at least 3 points")

    session = get_user_session(current_user["uid"])
    geofence = session["geofence"]
    camera_state = session["camera_state"]
    geofence.set_zone(config.points, config.name or "Zone A")
    set_active_zone_for_camera(
        session,
        camera_state["selected_camera_index"],
        config.name or "Zone A",
        config.points,
    )
    upsert_saved_zone(
        session,
        camera_state["selected_camera_index"],
        config.name or "Zone A",
        config.points,
    )
    return {"status": "zone updated", "zone": geofence.get_config()}


@app.delete("/zone", tags=["Geo Fence"])
async def clear_zone(current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    session["active_zone_by_camera"][camera_state["selected_camera_index"]] = None
    session["geofence"].clear()
    return {"status": "zone cleared"}


@app.get("/zones/presets", tags=["Geo Fence"])
async def list_zone_presets(camera_index: Optional[int] = None, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    resolved_camera_index = (
        camera_state["selected_camera_index"]
        if camera_index is None
        else camera_index
    )
    return {
        "camera_index": resolved_camera_index,
        "active_zone": get_active_zone_for_camera(session, resolved_camera_index),
        "zones": get_saved_zones(session, resolved_camera_index),
    }


@app.post("/zones/presets", tags=["Geo Fence"], responses={400: {"description": "Saved zone must have a name and at least three points"}})
async def save_zone_preset(body: SavedZoneRequest, current_user: dict = Depends(get_current_user)) -> dict:
    if len(body.points) < 3:
        raise HTTPException(400, "Saved zone needs at least 3 points")

    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    resolved_camera_index = (
        camera_state["selected_camera_index"]
        if body.camera_index is None
        else body.camera_index
    )
    zone = upsert_saved_zone(session, resolved_camera_index, body.name, body.points)
    return {
        "status": "saved",
        "camera_index": resolved_camera_index,
        "zone": zone,
        "zones": get_saved_zones(session, resolved_camera_index),
    }


@app.delete("/zones/presets", tags=["Geo Fence"], responses={404: {"description": "Saved zone preset not found"}})
async def remove_zone_preset(name: str, camera_index: Optional[int] = None, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    resolved_camera_index = (
        camera_state["selected_camera_index"]
        if camera_index is None
        else camera_index
    )
    deleted = delete_saved_zone(session, resolved_camera_index, name)
    if not deleted:
        raise HTTPException(404, f"Saved zone '{name}' was not found")
    return {
        "status": "deleted",
        "camera_index": resolved_camera_index,
        "zones": get_saved_zones(session, resolved_camera_index),
    }


@app.get("/alerts", tags=["Alerts"])
async def get_alerts(limit: int = 50, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    return {"alerts": session["alert_manager"].get_recent(limit)}


@app.delete("/alerts", tags=["Alerts"])
async def clear_alerts(current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    session["alert_manager"].clear()
    return {"status": "alerts cleared"}

@app.get("/storage/cameras", tags=["Storage"])
async def get_saved_camera_storage(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        snapshot = drive_storage.load_user_snapshot(current_user["uid"])
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "status": "loaded" if snapshot else "empty",
        "snapshot": snapshot,
        **extract_storage_payload(snapshot),
    }


@app.put("/storage/cameras", tags=["Storage"])
async def save_saved_camera_storage(
    body: CameraStorageRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    session = get_user_session(current_user["uid"])
    try:
        existing_snapshot = drive_storage.load_user_snapshot(current_user["uid"]) or {}
        snapshot = build_snapshot_payload(
            session,
            current_user,
            body.profile,
            saved_cameras=body.saved_cameras,
            last_selected_camera_id=body.last_selected_camera_id,
            existing_snapshot=existing_snapshot,
        )
        result = drive_storage.save_user_snapshot(current_user["uid"], snapshot)
        return {
            "status": "saved",
            "snapshot": snapshot,
            "file": result,
            **extract_storage_payload(snapshot),
        }
    except DriveConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/storage/snapshot", tags=["Storage"])
async def save_snapshot(body: SnapshotRequest, current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    try:
        existing_snapshot = drive_storage.load_user_snapshot(current_user["uid"]) or {}
        snapshot = build_snapshot_payload(
            session,
            current_user,
            body.profile,
            saved_cameras=body.saved_cameras,
            last_selected_camera_id=body.last_selected_camera_id,
            existing_snapshot=existing_snapshot,
        )
        result = drive_storage.save_user_snapshot(current_user["uid"], snapshot)
        return {
            "status": "saved",
            "snapshot": snapshot,
            "file": result,
            **extract_storage_payload(snapshot),
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
            **extract_storage_payload(snapshot),
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
        return {"status": "empty", "snapshot": None, **extract_storage_payload(None)}

    session = get_user_session(current_user["uid"])
    apply_snapshot(session, snapshot)
    return {
        "status": "restored",
        "snapshot": snapshot,
        "zone": session["geofence"].get_config(),
        **extract_storage_payload(snapshot),
    }


@app.get("/status", tags=["System"])
async def get_status(current_user: dict = Depends(get_current_user)) -> dict:
    session = get_user_session(current_user["uid"])
    camera_state = session["camera_state"]
    geofence = session["geofence"]
    alert_manager = session["alert_manager"]
    return {
        "camera_running": camera_state["running"],
        "selected_camera_index": camera_state["selected_camera_index"],
        "saved_zone_count": len(get_saved_zones(session, camera_state["selected_camera_index"])),
        "fps": camera_state["fps"],
        "zone_active": geofence.is_active(),
        "zone_name": geofence.name,
        "total_alerts": alert_manager.total_count(),
        "active_detections": len(camera_state["detections"]),
        "tracking_enabled": TRACKING_ENABLED,
        "preprocessing_enabled": PREPROCESSING_ENABLED,
        "last_error": camera_state["last_error"],
    }
