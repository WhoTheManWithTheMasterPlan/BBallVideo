"""
MViT v2-S basketball action classifier inference module.

Classifies 16-frame sequences into basketball actions using a fine-tuned
MViT v2-S model trained on the SpaceJam dataset.

Classes: block, pass, run, dribble, shoot, ball_in_hand, defence, pick,
         no_action, walk
"""

import json
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = "ml/models/action-classifier/mvit_v2_spacejam.pth"
DEFAULT_METADATA = "ml/models/action-classifier/training_metadata.json"

# Class index to name mapping
CLASS_NAMES = {
    0: "block",
    1: "pass",
    2: "run",
    3: "dribble",
    4: "shoot",
    5: "ball_in_hand",
    6: "defence",
    7: "pick",
    8: "no_action",
    9: "walk",
}

NUM_CLASSES = len(CLASS_NAMES)
NUM_FRAMES = 16
CROP_SIZE = 224

# Kinetics-400 normalization stats (same as training)
KINETICS_MEAN = [0.45, 0.45, 0.45]
KINETICS_STD = [0.225, 0.225, 0.225]


class ActionClassifier:
    """Classifies basketball actions from 16-frame video clips using MViT v2-S."""

    def __init__(self, weights_path: str | None = None, device: str | None = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        # Resolve weights path relative to project root
        if weights_path is None:
            # __file__ = backend/app/services/inference/action_classifier.py
            # 4 parents = backend/, 5 parents = project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            candidate = project_root / DEFAULT_WEIGHTS
            if candidate.exists():
                weights_path = str(candidate)
            else:
                raise FileNotFoundError(
                    f"Action classifier weights not found at {candidate}. "
                    f"Train with: python ml/train_action_classifier.py"
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
        logger.info(f"Action classifier loaded from {weights_path} on {self.device}")

        # Load metadata if available
        metadata_path = Path(weights_path).parent / "training_metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                self.metadata = json.load(f)
            logger.info(
                f"Training metadata: best_val_accuracy={self.metadata.get('best_val_accuracy', 'N/A')}%"
            )

        # Precompute normalization tensors
        self._mean = torch.tensor(KINETICS_MEAN).view(1, 3, 1, 1).to(self.device)
        self._std = torch.tensor(KINETICS_STD).view(1, 3, 1, 1).to(self.device)

    def _build_model(self) -> nn.Module:
        """Build MViT v2-S architecture with custom head (no pretrained weights)."""
        from torchvision.models.video import mvit_v2_s

        # Build without pretrained weights — we'll load our fine-tuned weights
        model = mvit_v2_s(weights=None)

        # MViT v2-S head is model.head[1]: Linear(768, 400)
        # Replace with our 10-class head
        in_features = model.head[1].in_features
        model.head[1] = nn.Linear(in_features, NUM_CLASSES)

        return model

    def preprocess(self, frames: list[np.ndarray]) -> torch.Tensor:
        """
        Preprocess a list of frames for MViT v2-S inference.

        Args:
            frames: List of 16 RGB or BGR numpy arrays (H, W, 3) uint8.
                    If fewer than 16 frames, the last frame is repeated.
                    If more than 16, frames are uniformly sampled.

        Returns:
            (1, C, T, H, W) float tensor ready for model input.
        """
        # Handle frame count
        if len(frames) == 0:
            raise ValueError("Empty frame list")

        if len(frames) < NUM_FRAMES:
            # Pad by repeating last frame
            while len(frames) < NUM_FRAMES:
                frames.append(frames[-1].copy())
        elif len(frames) > NUM_FRAMES:
            # Uniform temporal sampling
            indices = [int(i * len(frames) / NUM_FRAMES) for i in range(NUM_FRAMES)]
            frames = [frames[i] for i in indices]

        # Stack to (T, H, W, C) and convert
        video = np.stack(frames, axis=0)  # (T, H, W, C)
        video = torch.from_numpy(video).float() / 255.0  # (T, H, W, C)
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

        # Center crop
        _, _, new_h, new_w = video.shape
        top = (new_h - CROP_SIZE) // 2
        left = (new_w - CROP_SIZE) // 2
        video = video[:, :, top:top + CROP_SIZE, left:left + CROP_SIZE]

        # Normalize
        video = video.to(self.device)
        mean = self._mean.squeeze(0)  # (3, 1, 1)
        std = self._std.squeeze(0)
        video = (video - mean) / std
        if self.device == "cuda":
            video = video.half()

        # Reshape to (1, C, T, H, W)
        video = video.permute(1, 0, 2, 3).unsqueeze(0)  # (1, C, T, H, W)

        return video

    @torch.no_grad()
    def classify(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """
        Classify a 16-frame clip into a basketball action.

        Args:
            frames: List of consecutive video frames as numpy arrays (H, W, 3).
                    Frames should be RGB uint8. Can be player crops or
                    full-frame regions of interest.

        Returns:
            (action_name, confidence) — e.g. ("shoot", 0.87)
        """
        video = self.preprocess(frames)
        logits = self.model(video)  # (1, NUM_CLASSES)
        probs = torch.softmax(logits, dim=1)

        confidence, class_idx = probs.max(dim=1)
        action_name = CLASS_NAMES[class_idx.item()]
        conf = confidence.item()

        return action_name, conf

    @torch.no_grad()
    def classify_top_k(self, frames: list[np.ndarray], k: int = 3) -> list[tuple[str, float]]:
        """
        Return top-k predictions with confidence scores.

        Args:
            frames: List of consecutive video frames (H, W, 3) RGB uint8.
            k: Number of top predictions to return.

        Returns:
            List of (action_name, confidence) tuples, sorted by confidence desc.
        """
        video = self.preprocess(frames)
        logits = self.model(video)
        probs = torch.softmax(logits, dim=1).squeeze(0)

        topk_probs, topk_indices = probs.topk(k)
        results = [
            (CLASS_NAMES[idx.item()], prob.item())
            for prob, idx in zip(topk_probs, topk_indices)
        ]
        return results
