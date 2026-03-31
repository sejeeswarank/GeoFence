"""
Frame preprocessing before object detection.
"""

from __future__ import annotations

import cv2
import numpy as np

from config import (
    CLAHE_CLIP_LIMIT,
    CLAHE_TILE_GRID_SIZE,
    GAUSSIAN_BLUR_KERNEL,
    PREPROCESSING_ENABLED,
)


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    if not PREPROCESSING_ENABLED:
        return frame

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT,
        tileGridSize=CLAHE_TILE_GRID_SIZE,
    )
    lightness = clahe.apply(lightness)
    enhanced = cv2.merge((lightness, channel_a, channel_b))
    processed = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    if GAUSSIAN_BLUR_KERNEL > 1:
        kernel_size = GAUSSIAN_BLUR_KERNEL
        if kernel_size % 2 == 0:
            kernel_size += 1
        processed = cv2.GaussianBlur(processed, (kernel_size, kernel_size), 0)

    return processed
