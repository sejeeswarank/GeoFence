"""
Configuration for the GeoFence Vision pipeline.
"""

from pathlib import Path
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BASE_DIR = BACKEND_DIR
load_dotenv(PROJECT_ROOT / ".env")

# Camera and frame sizing
CAMERA_INDEX = 0
CAMERA_SCAN_LIMIT = 6
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
STREAM_JPEG_QUALITY = 75

# YOLOv8 inference
# Options: yolov8n.pt, yolov8s.pt, yolov8m.pt, yolov8l.pt
YOLO_MODEL = BACKEND_DIR / "yolov8n.pt"
CONFIDENCE_THRESHOLD = 0.2
YOLO_IMAGE_SIZE = 960

# COCO classes to track (empty set = track every class)
TARGET_CLASSES = {
    "person",
    "dog",
    "cat",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "bird",
}

# Preprocessing before detection
PREPROCESSING_ENABLED = False
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID_SIZE = (8, 8)
GAUSSIAN_BLUR_KERNEL = 3

# Lightweight centroid tracking
TRACKING_ENABLED = True
TRACKING_MAX_DISTANCE = 80
TRACKING_MAX_MISSES = 8

# Geo-fence defaults
DEFAULT_ZONE_POINTS = []
DEFAULT_ZONE_NAME = ""

# Alerting
MAX_ALERTS_STORED = 200
ALERT_COOLDOWN_SECONDS = 2.0

# UI assets
INDEX_HTML = FRONTEND_DIR / "index.html"
DASHBOARD_JS = FRONTEND_DIR / "dashboard.js"
LOGIN_HTML = FRONTEND_DIR / "login.html"
REGISTER_HTML = FRONTEND_DIR / "register.html"
LOGO_PNG = FRONTEND_DIR / "Geofence_logo.png"


