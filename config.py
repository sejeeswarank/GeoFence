"""
Configuration for the GeoFence Vision pipeline.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

# Camera and frame sizing
CAMERA_INDEX = 0
CAMERA_SCAN_LIMIT = 6
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
STREAM_JPEG_QUALITY = 75

# YOLOv8 inference
# Options: yolov8n.pt, yolov8s.pt, yolov8m.pt, yolov8l.pt
YOLO_MODEL = "yolov8n.pt"
CONFIDENCE_THRESHOLD = 0.45

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
    "zebra",
    "giraffe",
    "bird",
}

# Preprocessing before detection
PREPROCESSING_ENABLED = True
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID_SIZE = (8, 8)
GAUSSIAN_BLUR_KERNEL = 3

# Lightweight centroid tracking
TRACKING_ENABLED = True
TRACKING_MAX_DISTANCE = 80
TRACKING_MAX_MISSES = 8

# Geo-fence defaults
DEFAULT_ZONE_POINTS = [
    [150, 120],
    [490, 120],
    [490, 360],
    [150, 360],
]
DEFAULT_ZONE_NAME = "Zone A"

# Alerting
MAX_ALERTS_STORED = 200
ALERT_COOLDOWN_SECONDS = 2.0

# UI assets
INDEX_HTML = BASE_DIR / "index.html"
LOGIN_HTML = BASE_DIR / "login.html"
REGISTER_HTML = BASE_DIR / "register.html"
