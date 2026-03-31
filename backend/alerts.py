"""
Alert manager for safe and outside-zone status changes.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
import time

from config import ALERT_COOLDOWN_SECONDS, MAX_ALERTS_STORED


class AlertManager:
    def __init__(self) -> None:
        self._alerts = deque(maxlen=MAX_ALERTS_STORED)
        self._object_status: dict[str, str] = {}
        self._last_alert_time: dict[str, float] = {}
        self._total = 0

    def process(self, detections: list[dict], zone_name: str | None) -> None:
        if not zone_name:
            self._object_status.clear()
            return

        active_keys: set[str] = set()
        now = time.time()

        for detection in detections:
            object_key = str(detection.get("object_id") or detection["label"])
            active_keys.add(object_key)

            status = detection.get("zone_status", "safe")
            previous_status = self._object_status.get(object_key)

            should_log = previous_status is None or (
                previous_status is not None and previous_status != status
            )

            if should_log:
                cooldown_key = f"{object_key}:{status}"
                last_time = self._last_alert_time.get(cooldown_key, 0.0)
                if now - last_time >= ALERT_COOLDOWN_SECONDS:
                    self._log_event(detection, object_key, status, zone_name)
                    self._last_alert_time[cooldown_key] = now

            self._object_status[object_key] = status

        stale_keys = set(self._object_status) - active_keys
        for stale_key in stale_keys:
            self._object_status.pop(stale_key, None)

    def _log_event(self, detection: dict, object_key: str, status: str, zone_name: str) -> None:
        center_x, center_y = detection["center"]
        event = {
            "id": self._total + 1,
            "object_id": object_key,
            "label": detection["label"],
            "event": status,
            "confidence": detection["confidence"],
            "position": {"x": center_x, "y": center_y},
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "zone": zone_name,
        }
        self._alerts.appendleft(event)
        self._total += 1
        print(
            f"[Alert] #{object_key} {detection['label']} -> {status.upper()} at "
            f"({center_x}, {center_y}) in '{zone_name}'"
        )

    def get_recent(self, limit: int = 50) -> list[dict]:
        return list(self._alerts)[:limit]

    def clear(self) -> None:
        self._alerts.clear()
        self._object_status.clear()
        self._last_alert_time.clear()
        self._total = 0

    def total_count(self) -> int:
        return self._total

