"""
X3D-M basketball action classifier inference module.

Classifies 16-frame sequences into basketball actions using a fine-tuned
X3D-M model trained on the SpaceJam dataset.

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

DEFAULT_WEIGHTS = "ml/models/action-classifier/x3d_m_spacejam_best.pth"
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
    """Classifies basketball actions from 16-frame video clips using X3D-M."""

    def __init__(self, weights_path: str | None = None, device: str | None = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        # Resolve weights path relative to project root
        if weights_path is None:
            candidate = Path(__file__).parent.parent.parent.parent / DEFAULT_WEIGHTS
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
        """Build X3D-M architecture with custom head (no pretrained weights)."""
        try:
            model = torch.hub.load(
                "facebookresearch/pytorchvideo",
                model="x3d_m",
                pretrained=False,
            )
        except Exception:
            try:
                from pytorchvideo.models import x3d
                model = x3d.create_x3d(
                    input_clip_length=NUM_FRAMES,
                    input_crop_size=CROP_SIZE,
                    model_num_class=400,
                    dropout_rate=0.5,
                    width_factor=2.0,
                    depth_factor=2.2,
                )
            except ImportError:
                raise RuntimeError(
                    "Cannot load X3D-M architecture. Ensure torch.hub or "
                    "pytorchvideo is available."
                )

        # Replace classification head (same as training script)
        if hasattr(model, "blocks"):
            head_block = model.blocks[-1]
            if hasattr(head_block, "proj"):
                in_features = head_block.proj.in_features
                head_block.proj = nn.Linear(in_features, NUM_CLASSES)
                if hasattr(head_block, "activation"):
                    head_block.activation = nn.Identity()
            else:
                self._replace_head_fallback(model)
        else:
            self._replace_head_fallback(model)

        return model

    @staticmethod
    def _replace_head_fallback(model: nn.Module):
        """Find and replace any Linear(*, 400) layer."""
        for name, module in model.named_modules():
            if isinstance(module, nn.Linear) and module.out_features == 400:
                in_features = module.in_features
                parts = name.split(".")
                parent = model
                for part in parts[:-1]:
                    parent = getattr(parent, part)
                setattr(parent, parts[-1], nn.Linear(in_features, NUM_CLASSES))
                return
        raise RuntimeError("Could not find classification head to replace.")

    def preprocess(self, frames: list[np.ndarray]) -> torch.Tensor:
        """
        Preprocess a list of frames for X3D-M inference.

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

        # Detect BGR (OpenCV default) vs RGB — assume BGR if channel order unknown
        # The training pipeline uses RGB, so convert if needed
        # Caller should pass RGB; we handle both gracefully
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
