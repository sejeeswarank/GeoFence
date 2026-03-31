"""
Simple centroid tracker for stable object IDs across frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from config import TRACKING_ENABLED, TRACKING_MAX_DISTANCE, TRACKING_MAX_MISSES


@dataclass
class TrackState:
    track_id: int
    label: str
    center: tuple[int, int]
    bbox: list[int]
    confidence: float
    misses: int = 0


class ObjectTracker:
    def __init__(self) -> None:
        self.enabled = TRACKING_ENABLED
        self.max_distance = TRACKING_MAX_DISTANCE
        self.max_misses = TRACKING_MAX_MISSES
        self._next_track_id = 1
        self._tracks: dict[int, TrackState] = {}

    def reset(self) -> None:
        self._tracks.clear()
        self._next_track_id = 1

    def update(self, detections: list[dict]) -> list[dict]:
        if not detections:
            self._age_tracks()
            return detections

        if not self.enabled:
            for index, detection in enumerate(detections, start=1):
                detection["object_id"] = f"{detection['label']}-{index}"
            return detections

        assigned_tracks: set[int] = set()
        assigned_detections: set[int] = set()
        next_tracks: dict[int, TrackState] = {}

        for detection in sorted(
            enumerate(detections), key=lambda item: item[1]["confidence"], reverse=True
        ):
            original_index, payload = detection
            best_track_id = None
            best_distance = float(self.max_distance) + 1.0

            for track_id, track in self._tracks.items():
                if track_id in assigned_tracks or track.label != payload["label"]:
                    continue

                distance = hypot(
                    payload["center"][0] - track.center[0],
                    payload["center"][1] - track.center[1],
                )
                if distance <= self.max_distance and distance < best_distance:
                    best_distance = distance
                    best_track_id = track_id

            if best_track_id is None:
                continue

            payload["object_id"] = best_track_id
            assigned_tracks.add(best_track_id)
            assigned_detections.add(original_index)
            next_tracks[best_track_id] = TrackState(
                track_id=best_track_id,
                label=payload["label"],
                center=tuple(payload["center"]),
                bbox=payload["bbox"],
                confidence=payload["confidence"],
                misses=0,
            )

        for track_id, track in self._tracks.items():
            if track_id in assigned_tracks:
                continue

            misses = track.misses + 1
            if misses <= self.max_misses:
                next_tracks[track_id] = TrackState(
                    track_id=track.track_id,
                    label=track.label,
                    center=track.center,
                    bbox=track.bbox,
                    confidence=track.confidence,
                    misses=misses,
                )

        for index, detection in enumerate(detections):
            if index in assigned_detections:
                continue

            track_id = self._next_track_id
            self._next_track_id += 1
            detection["object_id"] = track_id
            next_tracks[track_id] = TrackState(
                track_id=track_id,
                label=detection["label"],
                center=tuple(detection["center"]),
                bbox=detection["bbox"],
                confidence=detection["confidence"],
                misses=0,
            )

        self._tracks = next_tracks
        return detections

    def _age_tracks(self) -> None:
        if not self.enabled:
            return

        next_tracks: dict[int, TrackState] = {}
        for track_id, track in self._tracks.items():
            misses = track.misses + 1
            if misses <= self.max_misses:
                next_tracks[track_id] = TrackState(
                    track_id=track.track_id,
                    label=track.label,
                    center=track.center,
                    bbox=track.bbox,
                    confidence=track.confidence,
                    misses=misses,
                )
        self._tracks = next_tracks
