"""
Polygon geo-fence handling and drawing helpers.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from shapely.geometry import Point, Polygon

from config import DEFAULT_ZONE_NAME, DEFAULT_ZONE_POINTS


class GeoFence:
    def __init__(self) -> None:
        self.points: list[list[int]] = []
        self.polygon: Optional[Polygon] = None
        self.name = DEFAULT_ZONE_NAME

        if DEFAULT_ZONE_POINTS:
            self.set_zone(DEFAULT_ZONE_POINTS, DEFAULT_ZONE_NAME)

    def set_zone(self, points: list[list[int]], name: str = "Zone A") -> None:
        self.points = points
        self.name = name
        self.polygon = Polygon([(point[0], point[1]) for point in points])
        print(f"[GeoFence] Zone '{self.name}' set with {len(self.points)} points")

    def clear(self) -> None:
        self.points = []
        self.polygon = None
        self.name = ""
        print("[GeoFence] Zone cleared")

    def is_active(self) -> bool:
        return self.polygon is not None and self.polygon.is_valid

    def is_inside(self, x: int, y: int) -> bool:
        if not self.is_active():
            return False
        return bool(self.polygon.covers(Point(x, y)))

    def get_config(self) -> dict:
        return {
            "active": self.is_active(),
            "name": self.name,
            "points": self.points,
            "area_px": int(self.polygon.area) if self.is_active() else 0,
        }

    def draw_zone(self, frame: np.ndarray) -> np.ndarray:
        if not self.is_active() or len(self.points) < 3:
            return frame

        points = np.array(self.points, dtype=np.int32)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [points], (0, 210, 140))
        frame = cv2.addWeighted(frame, 0.78, overlay, 0.22, 0)
        cv2.polylines(frame, [points], isClosed=True, color=(0, 230, 160), thickness=2)

        label_x, label_y = self.points[0]
        cv2.putText(
            frame,
            f"Zone: {self.name}",
            (label_x, max(24, label_y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 230, 160),
            2,
        )
        return frame
