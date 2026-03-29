"""
MViT v2-S basketball event classifier inference module.

Classifies 16-frame sequences into basketball game events.
Runs as a parallel detector alongside heuristic event detection,
proposing events that heuristics may miss (blocks, rebounds, hustles)
and confirming/challenging heuristic calls on overlapping event types.

Classes: made_basket, assist, steal, rebound, block, hustle, nothing
"""

import json
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = "ml/models/event-classifier/mvit_v2_event.pth"
DEFAULT_METADATA = "ml/models/event-classifier/training_metadata.json"

CLASS_NAMES = {
    0: "made_basket",
    1: "assist",
    2: "steal",
    3: "rebound",
    4: "block",
    5: "hustle",
    6: "nothing",
}

NUM_CLASSES = len(CLASS_NAMES)
NUM_FRAMES = 16
CROP_SIZE = 224

# Kinetics-400 normalization (same as training)
KINETICS_MEAN = [0.45, 0.45, 0.45]
KINETICS_STD = [0.225, 0.225, 0.225]

# Minimum confidence to emit an event (per class)
# Higher thresholds for classes with more false positives
CONFIDENCE_THRESHOLDS = {
    "made_basket": 0.7,
    "assist": 0.6,
    "steal": 0.6,
    "rebound": 0.6,
    "block": 0.6,
    "hustle": 0.6,
    "nothing": 1.1,  # Never emit "nothing" as an event
}


class EventClassifier:
    """Classifies basketball game events from 16-frame video clips using MViT v2-S."""

    def __init__(self, weights_path: str | None = None, device: str | None = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        # Resolve weights path relative to project root
        if weights_path is None:
            project_root = Path(__file__).parent.parent.parent.parent.parent
            candidate = project_root / DEFAULT_WEIGHTS
            if candidate.exists():
                weights_path = str(candidate)
            else:
                raise FileNotFoundError(
                    f"Event classifier weights not found at {candidate}. "
                    f"Train with: python -m ml.train_event_classifier"
                )

        # Load model architecture
        self.model = self._build_model()

        # Load trained weights
        state_dict = torch.load(weights_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        if self.device == "cuda":
            self.model = self.model.half()
        self.model.eval()
        logger.info(f"Event classifier loaded from {weights_path} on {self.device}")

        # Load metadata if available
        metadata_path = Path(weights_path).parent / "training_metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                self.metadata = json.load(f)
            logger.info(
                f"Event classifier metadata: best_val_accuracy="
                f"{self.metadata.get('results', {}).get('best_val_accuracy', 'N/A')}%"
            )

        # Precompute normalization tensors
        self._mean = torch.tensor(KINETICS_MEAN).view(1, 3, 1, 1).to(self.device)
        self._std = torch.tensor(KINETICS_STD).view(1, 3, 1, 1).to(self.device)

    def _build_model(self) -> nn.Module:
        """Build MViT v2-S architecture with 7-class event head."""
        from torchvision.models.video import mvit_v2_s

        model = mvit_v2_s(weights=None)
        in_features = model.head[1].in_features
        model.head[1] = nn.Linear(in_features, NUM_CLASSES)
        return model

    def preprocess(self, frames: list[np.ndarray]) -> torch.Tensor:
        """
        Preprocess frames for MViT v2-S inference.

        Args:
            frames: List of 16 RGB numpy arrays (H, W, 3) uint8.

        Returns:
            (1, C, T, H, W) float tensor ready for model input.
        """
        if len(frames) == 0:
            raise ValueError("Empty frame list")

        if len(frames) < NUM_FRAMES:
            while len(frames) < NUM_FRAMES:
                frames.append(frames[-1].copy())
        elif len(frames) > NUM_FRAMES:
            indices = [int(i * len(frames) / NUM_FRAMES) for i in range(NUM_FRAMES)]
            frames = [frames[i] for i in indices]

        video = np.stack(frames, axis=0)
        video = torch.from_numpy(video).float() / 255.0
        video = video.permute(0, 3, 1, 2)  # (T, C, H, W)

        # Resize short side to 256, then center crop to 224
        _, _, h, w = video.shape
        if h < w:
            new_h, new_w = 256, int(w * 256 / h)
        else:
            new_w, new_h = 256, int(h * 256 / w)

        video = torch.nn.functional.interpolate(
            video, size=(new_h, new_w), mode="bilinear", align_corners=False,
        )

        _, _, new_h, new_w = video.shape
        top = (new_h - CROP_SIZE) // 2
        left = (new_w - CROP_SIZE) // 2
        video = video[:, :, top:top + CROP_SIZE, left:left + CROP_SIZE]

        video = video.to(self.device)
        mean = self._mean.squeeze(0)
        std = self._std.squeeze(0)
        video = (video - mean) / std
        if self.device == "cuda":
            video = video.half()

        video = video.permute(1, 0, 2, 3).unsqueeze(0)  # (1, C, T, H, W)
        return video

    @torch.no_grad()
    def classify(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """
        Classify a 16-frame clip into a basketball event.

        Returns:
            (event_name, confidence) — e.g. ("made_basket", 0.92)
        """
        video = self.preprocess(frames)
        logits = self.model(video)
        probs = torch.softmax(logits, dim=1)

        confidence, class_idx = probs.max(dim=1)
        event_name = CLASS_NAMES[class_idx.item()]
        conf = confidence.item()

        return event_name, conf

    @torch.no_grad()
    def classify_all(self, frames: list[np.ndarray]) -> dict[str, float]:
        """
        Return confidence scores for all event classes.

        Returns:
            Dict of {event_name: confidence} for all 7 classes.
        """
        video = self.preprocess(frames)
        logits = self.model(video)
        probs = torch.softmax(logits, dim=1).squeeze(0)

        return {CLASS_NAMES[i]: probs[i].item() for i in range(NUM_CLASSES)}

    def should_emit(self, event_name: str, confidence: float) -> bool:
        """Check if an event prediction meets the emission threshold."""
        threshold = CONFIDENCE_THRESHOLDS.get(event_name, 0.7)
        return confidence >= threshold
