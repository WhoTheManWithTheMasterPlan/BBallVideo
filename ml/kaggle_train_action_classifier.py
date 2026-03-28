"""
Kaggle Notebook: Fine-tune MViT v2-S on SpaceJam Basketball Action Recognition
================================================================================

SETUP INSTRUCTIONS:
1. Go to https://www.kaggle.com/code and create a new notebook.
2. Click "Add Data" (right panel) and search for "spacejam-action-recognition".
   Attach the dataset. It will be mounted at /kaggle/input/spacejam-action-recognition/.
   Expected layout:
     /kaggle/input/datasets/adamschaechter/spacejam-action-recognition/
       examples/                    (37K+ mp4 clips)
       annotation_dict.json
       labels_dict.json
       testset_keys_1lug2020.txt
3. Under Settings, set Accelerator to "GPU T4 x2" or "GPU T4".
4. Paste this entire script into a single code cell and run it.

SESSION LIMITS:
- Kaggle GPU sessions are 12 hours max.
- This script auto-saves a checkpoint after every epoch and will gracefully
  stop if approaching 11.5 hours elapsed.

RESUMING AFTER DISCONNECT:
- Just re-run the notebook. The script detects checkpoint_state.pth in
  /kaggle/working/ and resumes from the last completed epoch, restoring
  model weights, optimizer state, scheduler state, and best accuracy.

OUTPUTS (in /kaggle/working/):
- mvit_v2_spacejam.pth          Best model weights
- checkpoint_state.pth          Full training state for resume
- training_metadata.json        Training config and results
- training.log                  Complete training log
"""

import ast
import json
import logging
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

# ─── Logging: dual output to stdout + file ─────────────────────────────
LOG_PATH = Path("/kaggle/working/training.log")

logger = logging.getLogger("kaggle_train")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(formatter)
logger.addHandler(stdout_handler)

file_handler = logging.FileHandler(str(LOG_PATH), mode="a")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ─── Configuration ──────────────────────────────────────────────────────

# Kaggle paths — auto-discover dataset root
INPUT_BASE = Path("/kaggle/input/datasets/adamschaechter/spacejam-action-recognition")
OUTPUT_DIR = Path("/kaggle/working")

# Find where the actual files are (top-level or one subfolder down)
def find_dataset_root(base: Path) -> Path:
    """Find the directory containing annotation_dict.json."""
    if (base / "annotation_dict.json").exists():
        return base
    for child in base.iterdir():
        if child.is_dir() and (child / "annotation_dict.json").exists():
            return child
    raise FileNotFoundError(
        f"Cannot find annotation_dict.json under {base}. "
        f"Contents: {[p.name for p in base.iterdir()]}"
    )

SPACEJAM_DIR = find_dataset_root(INPUT_BASE)
DATA_DIR = SPACEJAM_DIR / "examples"  # SpaceJam dataset uses "examples/" for mp4 clips
ANNOTATION_PATH = SPACEJAM_DIR / "annotation_dict.json"
LABELS_PATH = SPACEJAM_DIR / "labels_dict.json"
TESTSET_KEYS_PATH = SPACEJAM_DIR / "testset_keys_1lug2020.txt"

CHECKPOINT_PATH = OUTPUT_DIR / "mvit_v2_spacejam.pth"
CHECKPOINT_STATE_PATH = OUTPUT_DIR / "checkpoint_state.pth"
METADATA_PATH = OUTPUT_DIR / "training_metadata.json"

# Class 10 ("discard") is excluded from training.
DISCARD_CLASS = 10

# Training hyperparameters
BATCH_SIZE = 8          # T4 16GB VRAM can handle 8
NUM_EPOCHS = 30
LEARNING_RATE = 5e-5
WEIGHT_DECAY = 0.05
NUM_WORKERS = 2         # Kaggle Linux environment supports multiprocessing
VAL_SPLIT = 0.1
SEED = 42

# MViT v2-S input requirements
NUM_FRAMES = 16
CROP_SIZE = 224
RESIZE_SHORT = 256

# Kinetics-400 normalization
KINETICS_MEAN = [0.45, 0.45, 0.45]
KINETICS_STD = [0.225, 0.225, 0.225]

# Session time limit — stop gracefully before Kaggle kills us
SESSION_START_TIME = time.time()
MAX_SESSION_SECONDS = 11.5 * 3600  # 11.5 hours


# ─── Dataset Loading ────────────────────────────────────────────────────

def load_spacejam_annotations() -> tuple:
    """Load annotation_dict and labels_dict using ast.literal_eval."""
    if not ANNOTATION_PATH.exists():
        raise FileNotFoundError(f"Annotation file not found: {ANNOTATION_PATH}")
    if not LABELS_PATH.exists():
        raise FileNotFoundError(f"Labels file not found: {LABELS_PATH}")

    with open(ANNOTATION_PATH, "r") as f:
        annotations = ast.literal_eval(f.read())
    with open(LABELS_PATH, "r") as f:
        labels = ast.literal_eval(f.read())

    logger.info(f"Loaded {len(annotations)} annotations, {len(labels)} classes")
    return annotations, labels


def load_test_keys() -> set:
    """Load the test-split clip IDs from testset_keys_1lug2020.txt."""
    if not TESTSET_KEYS_PATH.exists():
        raise FileNotFoundError(f"Test keys file not found: {TESTSET_KEYS_PATH}")

    with open(TESTSET_KEYS_PATH, "r") as f:
        content = f.read().strip()

    test_keys = ast.literal_eval(content)

    if isinstance(test_keys, list):
        test_keys = set(str(k) for k in test_keys)
    else:
        raise ValueError(f"Expected list in {TESTSET_KEYS_PATH}, got {type(test_keys)}")

    logger.info(f"Loaded {len(test_keys)} test-split keys")
    return test_keys


def build_clip_list(annotations, labels, test_keys):
    """
    Build train+val and test clip lists from annotations and data directory.

    - Maps annotation clip IDs to mp4 files in data/
    - Also picks up _flipped variants (same label as base clip)
    - Excludes class 10 (discard)
    - Remaps class indices to contiguous 0..(N-1)
    """
    kept_classes = sorted(k for k in labels.keys() if k != DISCARD_CLASS)
    original_to_new = {orig: new for new, orig in enumerate(kept_classes)}
    class_names = [labels[orig] for orig in kept_classes]
    num_classes = len(class_names)

    logger.info(f"Keeping {num_classes} classes (excluding '{labels.get(DISCARD_CLASS, 'discard')}')")
    for new_idx, name in enumerate(class_names):
        orig_idx = kept_classes[new_idx]
        logger.info(f"  {orig_idx} -> {new_idx}: {name}")

    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")

    mp4_files = {p.stem: p for p in DATA_DIR.iterdir() if p.suffix == ".mp4"}
    logger.info(f"Found {len(mp4_files)} mp4 files in {DATA_DIR}")

    trainval_clips = []
    test_clips = []
    skipped_discard = 0
    skipped_missing = 0
    flipped_added = 0

    for clip_id, class_idx in annotations.items():
        clip_id_str = str(clip_id)

        if class_idx == DISCARD_CLASS:
            skipped_discard += 1
            continue

        if class_idx not in original_to_new:
            logger.warning(f"Unknown class {class_idx} for clip {clip_id_str}, skipping")
            continue

        new_label = original_to_new[class_idx]
        is_test = clip_id_str in test_keys

        if clip_id_str in mp4_files:
            clip_path = mp4_files[clip_id_str]
            if is_test:
                test_clips.append((clip_path, new_label))
            else:
                trainval_clips.append((clip_path, new_label))
        else:
            skipped_missing += 1

        flipped_id = f"{clip_id_str}_flipped"
        if flipped_id in mp4_files:
            flipped_path = mp4_files[flipped_id]
            if is_test:
                test_clips.append((flipped_path, new_label))
            else:
                trainval_clips.append((flipped_path, new_label))
                flipped_added += 1

    logger.info(f"Clips built: {len(trainval_clips)} train+val, {len(test_clips)} test")
    logger.info(f"  Skipped {skipped_discard} discard-class clips")
    logger.info(f"  Skipped {skipped_missing} clips with no matching mp4 file")
    logger.info(f"  Added {flipped_added} flipped augmentation clips to train+val")

    tv_counts = Counter(c[1] for c in trainval_clips)
    test_counts = Counter(c[1] for c in test_clips)
    logger.info("Train+Val class distribution:")
    for idx in range(num_classes):
        logger.info(f"  {class_names[idx]:20s}: {tv_counts.get(idx, 0):6d}")
    logger.info("Test class distribution:")
    for idx in range(num_classes):
        logger.info(f"  {class_names[idx]:20s}: {test_counts.get(idx, 0):6d}")

    return trainval_clips, test_clips, class_names, original_to_new


# ─── Dataset ────────────────────────────────────────────────────────────

class SpaceJamDataset(Dataset):
    """
    Loads SpaceJam mp4 clips from disk.

    Each item is a (video_tensor, label) pair where the video tensor is
    (C, T, H, W) float, normalized for Kinetics-400.
    """

    def __init__(self, clips, transform=None):
        self.clips = clips
        self.transform = transform

    def __len__(self):
        return len(self.clips)

    def __getitem__(self, idx):
        clip_path, label = self.clips[idx]
        frames = self._load_frames(clip_path)

        if self.transform is not None:
            frames = self.transform(frames)
        else:
            frames = torch.from_numpy(frames).permute(3, 0, 1, 2).float() / 255.0

        return frames, label

    def _load_frames(self, video_path):
        """Load NUM_FRAMES frames from an mp4 file. Returns (T, H, W, C) uint8."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        all_frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            all_frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        cap.release()

        if len(all_frames) == 0:
            raise ValueError(f"No frames decoded from: {video_path}")

        indices = self._sample_indices(len(all_frames), NUM_FRAMES)
        frames = [all_frames[i] for i in indices]
        return np.stack(frames, axis=0)

    @staticmethod
    def _sample_indices(total, num):
        """Uniformly sample `num` indices from [0, total)."""
        if total >= num:
            return [int(i * total / num) for i in range(num)]
        else:
            indices = list(range(total))
            while len(indices) < num:
                indices.append(total - 1)
            return indices


# ─── Transforms ─────────────────────────────────────────────────────────

class VideoTransform:
    """
    Video data augmentation and normalization.

    Operates on (T, H, W, C) uint8 numpy arrays.
    Returns (C, T, H, W) float tensors normalized for Kinetics-400.
    """

    def __init__(self, is_train=True):
        self.is_train = is_train
        self.crop_size = CROP_SIZE
        self.resize_short = RESIZE_SHORT

    def __call__(self, frames):
        # Convert to float [0, 1]
        video = torch.from_numpy(frames).float() / 255.0  # (T, H, W, C)
        T_len, H, W, C = video.shape

        # Resize short side
        if H < W:
            new_h = self.resize_short
            new_w = int(W * self.resize_short / H)
        else:
            new_w = self.resize_short
            new_h = int(H * self.resize_short / W)

        video = video.permute(0, 3, 1, 2)  # (T, C, H, W)
        video = torch.nn.functional.interpolate(
            video, size=(new_h, new_w), mode="bilinear", align_corners=False,
        )

        _, _, new_h, new_w = video.shape

        if self.is_train:
            # Random crop
            top = random.randint(0, max(0, new_h - self.crop_size))
            left = random.randint(0, max(0, new_w - self.crop_size))
            video = video[:, :, top:top + self.crop_size, left:left + self.crop_size]

            # Random horizontal flip
            if random.random() > 0.5:
                video = torch.flip(video, dims=[3])

            # Color jitter (brightness + contrast)
            brightness_factor = 1.0 + random.uniform(-0.2, 0.2)
            contrast_factor = 1.0 + random.uniform(-0.2, 0.2)
            video = video * brightness_factor
            mean = video.mean(dim=(2, 3), keepdim=True)
            video = (video - mean) * contrast_factor + mean
            video = video.clamp(0, 1)
        else:
            # Center crop
            top = (new_h - self.crop_size) // 2
            left = (new_w - self.crop_size) // 2
            video = video[:, :, top:top + self.crop_size, left:left + self.crop_size]

        # Normalize with Kinetics-400 stats
        mean = torch.tensor(KINETICS_MEAN).view(1, 3, 1, 1)
        std = torch.tensor(KINETICS_STD).view(1, 3, 1, 1)
        video = (video - mean) / std

        # (T, C, H, W) -> (C, T, H, W) for MViT v2
        video = video.permute(1, 0, 2, 3)

        return video


# ─── Model ──────────────────────────────────────────────────────────────

def build_mvit_model(num_classes, device):
    """
    Load MViT v2-S pretrained on Kinetics-400 and replace the classification head.
    """
    from torchvision.models.video import mvit_v2_s, MViT_V2_S_Weights

    logger.info("Loading MViT v2-S pretrained on Kinetics-400 (torchvision)...")
    model = mvit_v2_s(weights=MViT_V2_S_Weights.KINETICS400_V1)

    # MViT v2 head is model.head[1] -- a Linear(768, 400)
    in_features = model.head[1].in_features
    model.head[1] = nn.Linear(in_features, num_classes)
    logger.info(f"Replaced head: Linear({in_features}, 400) -> Linear({in_features}, {num_classes})")

    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Parameters: {total_params:,} total, {trainable_params:,} trainable")

    return model


# ─── Training ───────────────────────────────────────────────────────────

def train_one_epoch(model, loader, criterion, optimizer, device, epoch):
    """Train for one epoch. Returns average loss."""
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (videos, labels) in enumerate(loader):
        videos = videos.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        outputs = model(videos)
        loss = criterion(outputs, labels)
        loss.backward()

        # Gradient clipping -- standard for transformer fine-tuning
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

        optimizer.step()

        total_loss += loss.item() * videos.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)

        if (batch_idx + 1) % 100 == 0:
            acc = 100.0 * correct / total
            logger.info(
                f"  Epoch {epoch} [{batch_idx + 1}/{len(loader)}] "
                f"Loss: {loss.item():.4f}  Acc: {acc:.1f}%"
            )

    avg_loss = total_loss / total
    accuracy = 100.0 * correct / total
    logger.info(f"  Train -- Loss: {avg_loss:.4f}, Accuracy: {accuracy:.1f}%")
    return avg_loss


@torch.no_grad()
def validate(model, loader, criterion, device):
    """Validate model. Returns (avg_loss, accuracy)."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for videos, labels in loader:
        videos = videos.to(device)
        labels = labels.to(device)

        outputs = model(videos)
        loss = criterion(outputs, labels)

        total_loss += loss.item() * videos.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)

    avg_loss = total_loss / total
    accuracy = 100.0 * correct / total
    return avg_loss, accuracy


def format_time(seconds):
    """Format seconds into HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def time_remaining_in_session():
    """Return seconds remaining before we hit the safety cutoff."""
    elapsed = time.time() - SESSION_START_TIME
    return MAX_SESSION_SECONDS - elapsed


def save_checkpoint(model, optimizer, scheduler, epoch, best_val_acc, best_epoch):
    """Save full training state for resume."""
    state = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "epoch": epoch,
        "best_val_acc": best_val_acc,
        "best_epoch": best_epoch,
    }
    torch.save(state, CHECKPOINT_STATE_PATH)
    logger.info(f"  Checkpoint saved: epoch {epoch}, best_val_acc={best_val_acc:.1f}%")


def load_checkpoint(model, optimizer, scheduler, device):
    """Load checkpoint if it exists. Returns (start_epoch, best_val_acc, best_epoch) or None."""
    if not CHECKPOINT_STATE_PATH.exists():
        return None

    logger.info(f"Found checkpoint at {CHECKPOINT_STATE_PATH}, resuming...")
    state = torch.load(CHECKPOINT_STATE_PATH, map_location=device, weights_only=False)

    model.load_state_dict(state["model_state_dict"])
    optimizer.load_state_dict(state["optimizer_state_dict"])
    scheduler.load_state_dict(state["scheduler_state_dict"])

    epoch = state["epoch"]
    best_val_acc = state["best_val_acc"]
    best_epoch = state["best_epoch"]

    logger.info(f"Resumed from epoch {epoch}, best_val_acc={best_val_acc:.1f}% (epoch {best_epoch})")
    return epoch, best_val_acc, best_epoch


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("SpaceJam Action Recognition — MViT v2-S Fine-tuning (Kaggle)")
    logger.info("=" * 60)

    # Reproducibility
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"torch.cuda.is_available() = {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
    if device != "cuda":
        logger.error("No CUDA GPU detected. Training on CPU is not supported.")
        logger.error("On Kaggle: Settings → Accelerator → select 'GPU T4 x2', then RESTART the session.")
        raise RuntimeError("No CUDA GPU detected. Enable GPU in Kaggle settings and restart the session.")

    logger.info(f"Device: {device}")
    logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
    logger.info(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    logger.info(f"PyTorch: {torch.__version__}")
    logger.info(f"Dataset root: {SPACEJAM_DIR}")
    logger.info(f"Output dir: {OUTPUT_DIR}")

    # ── Load annotations and build clip lists ──
    annotations, labels_dict = load_spacejam_annotations()
    test_keys = load_test_keys()
    trainval_clips, test_clips, class_names, original_to_new = build_clip_list(
        annotations, labels_dict, test_keys,
    )
    num_classes = len(class_names)

    if len(trainval_clips) == 0:
        logger.error("No training clips found. Check dataset at: %s", SPACEJAM_DIR)
        raise RuntimeError(f"No training clips found at {SPACEJAM_DIR}")

    # ── Train / Val split (90/10 of non-test) ──
    # Use a fixed seed shuffle so train/val split is identical across resumes
    rng = random.Random(SEED)
    trainval_clips_shuffled = list(trainval_clips)
    rng.shuffle(trainval_clips_shuffled)

    n_val = int(len(trainval_clips_shuffled) * VAL_SPLIT)
    n_train = len(trainval_clips_shuffled) - n_val

    train_clips = trainval_clips_shuffled[:n_train]
    val_clips = trainval_clips_shuffled[n_train:]

    train_dataset = SpaceJamDataset(train_clips, transform=VideoTransform(is_train=True))
    val_dataset = SpaceJamDataset(val_clips, transform=VideoTransform(is_train=False))
    test_dataset = SpaceJamDataset(test_clips, transform=VideoTransform(is_train=False))

    logger.info(f"Splits -- Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=True,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )

    # ── Build model ──
    model = build_mvit_model(num_classes, device)

    # ── Optimizer, scheduler, loss ──
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    scheduler = CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS, eta_min=1e-6)
    criterion = nn.CrossEntropyLoss()

    # ── Resume from checkpoint if available ──
    start_epoch = 0
    best_val_acc = 0.0
    best_epoch = 0

    checkpoint_data = load_checkpoint(model, optimizer, scheduler, device)
    if checkpoint_data is not None:
        start_epoch, best_val_acc, best_epoch = checkpoint_data

    # ── Training loop ──
    logger.info(f"\nStarting training: epochs {start_epoch + 1} to {NUM_EPOCHS}")
    logger.info(f"Model: MViT v2-S | Batch size: {BATCH_SIZE} | LR: {LEARNING_RATE} | WD: {WEIGHT_DECAY}")
    logger.info(f"Saving best model to: {CHECKPOINT_PATH}")
    logger.info(f"Session time budget: {format_time(MAX_SESSION_SECONDS)}\n")

    epoch_times = []
    stopped_early = False

    for epoch in range(start_epoch + 1, NUM_EPOCHS + 1):
        t0 = time.time()

        logger.info(f"Epoch {epoch}/{NUM_EPOCHS} (lr={optimizer.param_groups[0]['lr']:.2e})")
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device, epoch)
        val_loss, val_acc = validate(model, val_loader, criterion, device)
        scheduler.step()

        epoch_time = time.time() - t0
        epoch_times.append(epoch_time)

        # Progress stats
        avg_epoch_time = sum(epoch_times) / len(epoch_times)
        epochs_remaining = NUM_EPOCHS - epoch
        est_remaining = avg_epoch_time * epochs_remaining
        session_elapsed = time.time() - SESSION_START_TIME

        logger.info(
            f"  Val   -- Loss: {val_loss:.4f}, Accuracy: {val_acc:.1f}% "
            f"(epoch time: {format_time(epoch_time)})"
        )
        logger.info(
            f"  Progress: {epoch}/{NUM_EPOCHS} | "
            f"Avg epoch: {format_time(avg_epoch_time)} | "
            f"Est remaining: {format_time(est_remaining)} | "
            f"Session elapsed: {format_time(session_elapsed)}"
        )

        # Save best model
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch
            torch.save(model.state_dict(), CHECKPOINT_PATH)
            logger.info(f"  ** New best model saved (val_acc={val_acc:.1f}%)")

        logger.info(
            f"  Best so far: epoch {best_epoch} with val_acc={best_val_acc:.1f}%"
        )

        # Save checkpoint for resume
        save_checkpoint(model, optimizer, scheduler, epoch, best_val_acc, best_epoch)

        # Time check: stop if next epoch would exceed session limit
        remaining_session = time_remaining_in_session()
        if remaining_session < avg_epoch_time * 1.2:  # 20% safety margin
            logger.info(
                f"\n** TIME LIMIT: Only {format_time(remaining_session)} left in session, "
                f"avg epoch takes {format_time(avg_epoch_time)}. Stopping early."
            )
            stopped_early = True
            break

        logger.info("")  # blank line between epochs

    # ── Final test evaluation ──
    if not stopped_early or CHECKPOINT_PATH.exists():
        logger.info("\nEvaluating best model on test set...")
        if CHECKPOINT_PATH.exists():
            model.load_state_dict(torch.load(CHECKPOINT_PATH, map_location=device, weights_only=True))
        test_loss, test_acc = validate(model, test_loader, criterion, device)
        logger.info(f"Test -- Loss: {test_loss:.4f}, Accuracy: {test_acc:.1f}%")
    else:
        test_acc = -1.0
        logger.info("No best model checkpoint found, skipping test evaluation.")

    # ── Save training metadata ──
    completed_epochs = epoch if 'epoch' in dir() else start_epoch
    metadata = {
        "model": "mvit_v2_s",
        "pretrained_on": "kinetics-400",
        "dataset": "spacejam",
        "num_classes": num_classes,
        "class_names": class_names,
        "class_mapping": {str(k): v for k, v in original_to_new.items()},
        "excluded_classes": {str(DISCARD_CLASS): labels_dict.get(DISCARD_CLASS, "discard")},
        "best_epoch": best_epoch,
        "best_val_accuracy": best_val_acc,
        "test_accuracy": test_acc,
        "completed_epochs": completed_epochs,
        "target_epochs": NUM_EPOCHS,
        "stopped_early": stopped_early,
        "batch_size": BATCH_SIZE,
        "learning_rate": LEARNING_RATE,
        "weight_decay": WEIGHT_DECAY,
        "input_frames": NUM_FRAMES,
        "crop_size": CROP_SIZE,
        "kinetics_mean": KINETICS_MEAN,
        "kinetics_std": KINETICS_STD,
        "train_clips": len(train_clips),
        "val_clips": len(val_clips),
        "test_clips": len(test_clips),
        "total_training_time_seconds": time.time() - SESSION_START_TIME,
        "avg_epoch_time_seconds": sum(epoch_times) / len(epoch_times) if epoch_times else 0,
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("Training complete!")
    logger.info(f"Best model: epoch {best_epoch}, val accuracy: {best_val_acc:.1f}%")
    if test_acc >= 0:
        logger.info(f"Test accuracy: {test_acc:.1f}%")
    logger.info(f"Weights:  {CHECKPOINT_PATH}")
    logger.info(f"State:    {CHECKPOINT_STATE_PATH}")
    logger.info(f"Metadata: {METADATA_PATH}")
    logger.info(f"Log:      {LOG_PATH}")
    if stopped_early:
        logger.info(f"NOTE: Stopped early at epoch {completed_epochs}/{NUM_EPOCHS} due to session time limit.")
        logger.info("Re-run this notebook to resume from the checkpoint.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
else:
    # When pasted directly into a Kaggle notebook cell (not as __main__),
    # just call main() directly.
    main()
