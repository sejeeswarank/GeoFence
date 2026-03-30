"""
YOLOv8 object detector wrapper.
"""

from __future__ import annotations

from ultralytics import YOLO
import numpy as np

from config import CONFIDENCE_THRESHOLD, TARGET_CLASSES, YOLO_MODEL


class ObjectDetector:
    def __init__(self) -> None:
        print(f"[Detector] Loading YOLO model: {YOLO_MODEL}")
        self.model = YOLO(YOLO_MODEL)
        self.target_classes = TARGET_CLASSES
        print(f"[Detector] Tracking classes: {sorted(self.target_classes) or 'ALL'}")

    def detect(self, frame: np.ndarray) -> list[dict]:
        results = self.model(frame, verbose=False)[0]
        detections: list[dict] = []

        for box in results.boxes:
            label = self.model.names[int(box.cls)]
            confidence = float(box.conf)

            if confidence < CONFIDENCE_THRESHOLD:
                continue
            if self.target_classes and label not in self.target_classes:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            detections.append(
                {
                    "label": label,
                    "confidence": round(confidence, 3),
                    "bbox": [x1, y1, x2, y2],
                    "center": [center_x, center_y],
                    "object_id": None,
                    "inside_zone": False,
                    "zone_status": "safe",
                }
            )

        return detections
