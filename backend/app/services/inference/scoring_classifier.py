"""
ResNet50-based basketball scoring classifier.

Crops the hoop region each frame and classifies whether a score occurred.
Based on isBre/Automated-Basketball-Highlights-with-Deep-Learning.

The model outputs a per-frame confidence [0, 1] that a basket was scored.
Temporal peak detection (scipy.signal.find_peaks) identifies actual scoring events
from the confidence signal, filtering out noise and near-duplicates.
"""

import logging
from collections import deque
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms
from torchvision.models import resnet50

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = "ml/models/scoring-classifier/resnet50_cropped.pth"

# Crop size: 64px in each direction from hoop center = 128x128
CROP_HALF = 64


class ScoringClassifier:
    """Classifies whether a basket was scored by analyzing the hoop region."""

    def __init__(self, weights_path: str | None = None, device: str | None = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        # Resolve weights path
        if weights_path is None:
            # Try relative to project root
            candidate = Path(__file__).parent.parent.parent.parent / DEFAULT_WEIGHTS
            if candidate.exists():
                weights_path = str(candidate)
            else:
                raise FileNotFoundError(
                    f"Scoring classifier weights not found at {candidate}. "
                    f"Download with: gdown 1-DFR1P1hooQL8gzGmkmr5wzBMjcGwjh5"
                )

        # Build model: ResNet50 with binary output
        self.model = resnet50(weights=None)
        self.model.fc = nn.Sequential(
            nn.Linear(2048, 1),
            nn.Sigmoid(),
        )

        # Load weights
        state_dict = torch.load(weights_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        logger.info(f"Scoring classifier loaded from {weights_path} on {self.device}")

        # Preprocessing: same as isBre training pipeline
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Resize([128, 128], antialias=True),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ])

        # Per-frame confidence history for peak detection
        self.frame_confidences: list[float] = []

    def classify_frame(self, frame_rgb: np.ndarray,
                       hoop_bbox: tuple[float, float, float, float] | None) -> float:
        """Classify a single frame. Returns scoring confidence [0, 1].

        Args:
            frame_rgb: RGB frame (H, W, 3)
            hoop_bbox: Hoop bounding box (x1, y1, x2, y2) or None if no hoop detected
        """
        if hoop_bbox is None:
            self.frame_confidences.append(0.0)
            return 0.0

        # Crop hoop region
        crop = self._crop_hoop(frame_rgb, hoop_bbox)
        if crop is None:
            self.frame_confidences.append(0.0)
            return 0.0

        # Run classifier
        try:
            tensor = self.transform(crop).unsqueeze(0).to(self.device)
            with torch.no_grad():
                confidence = self.model(tensor).item()
        except RuntimeError:
            # Crop too small for convolution kernels
            confidence = 0.0

        self.frame_confidences.append(confidence)
        return confidence

    def _crop_hoop(self, frame_rgb: np.ndarray,
                   hoop_bbox: tuple[float, float, float, float]) -> np.ndarray | None:
        """Crop a 128x128 region centered on the hoop."""
        h, w = frame_rgb.shape[:2]
        x1, y1, x2, y2 = hoop_bbox
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)

        # Dynamic crop size based on hoop bbox size (handles different camera distances)
        hoop_w = x2 - x1
        hoop_h = y2 - y1
        crop_half = max(CROP_HALF, int(max(hoop_w, hoop_h) * 1.5))

        # Clamp to frame bounds
        crop_y1 = max(0, cy - crop_half)
        crop_y2 = min(h, cy + crop_half)
        crop_x1 = max(0, cx - crop_half)
        crop_x2 = min(w, cx + crop_half)

        crop = frame_rgb[crop_y1:crop_y2, crop_x1:crop_x2]

        if crop.shape[0] < 32 or crop.shape[1] < 32:
            return None

        return crop

    def get_scoring_events(self, fps: float = 30.0,
                           confidence_threshold: float = 0.5,
                           min_distance_seconds: float = 3.0) -> list[dict]:
        """Run peak detection on accumulated frame confidences.

        Call this after processing all frames to get the final scoring events.

        Returns list of {frame_idx, timestamp, confidence}.
        """
        from scipy.signal import find_peaks

        if not self.frame_confidences:
            return []

        confidences = np.array(self.frame_confidences)
        min_distance_frames = int(fps * min_distance_seconds)

        peaks, properties = find_peaks(
            confidences,
            height=confidence_threshold,
            distance=min_distance_frames,
        )

        events = []
        for peak_idx in peaks:
            events.append({
                "frame_idx": int(peak_idx),
                "timestamp": peak_idx / fps,
                "confidence": float(confidences[peak_idx]),
            })

        logger.info(f"Scoring classifier: {len(events)} events from {len(confidences)} frames "
                    f"(threshold={confidence_threshold}, min_gap={min_distance_seconds}s)")
        return events

    def reset(self):
        """Clear frame confidence history."""
        self.frame_confidences.clear()
