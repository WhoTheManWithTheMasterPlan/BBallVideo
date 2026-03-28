"""
Train YOLOv8x-pose on basketball court keypoint detection.

Uses a Roboflow dataset of annotated basketball court images with 18 keypoints
(corners, free throw lines, midcourt, paint edges).

Usage:
    python -m ml.train_court_detector

The trained model will be saved to ml/models/court-detector/best.pt

Roboflow dataset options (set ROBOFLOW_API_KEY env var):
  - "basketball-court-detection-fevi7" by FYP (203 images, 18 keypoints)
  - "basketball_keypoint_detection" by vayvay (351 images)
"""

import os
import sys
from pathlib import Path

# Patch platform before importing ultralytics (WMI hang on Win11+Py3.14)
try:
    import ml.patch_platform  # noqa: F401
except ImportError:
    pass

from ultralytics import YOLO

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "ml" / "models" / "court-detector"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Roboflow dataset config
ROBOFLOW_WORKSPACE = "fyp-3bwmg"
ROBOFLOW_PROJECT = "basketball-court-detection-fevi7"
ROBOFLOW_VERSION = 1
DATASET_DIR = PROJECT_ROOT / "ml" / "datasets" / "court-keypoints"

# Training config
MODEL = "yolov8x-pose.pt"  # Large model for best keypoint accuracy
EPOCHS = 200
IMGSZ = 640
BATCH = 8  # Adjust based on VRAM (8 for 8GB, 16 for 16GB)


def download_dataset():
    """Download court keypoint dataset from Roboflow."""
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("ERROR: Set ROBOFLOW_API_KEY environment variable.")
        print("Get your free API key at https://app.roboflow.com/settings/api")
        sys.exit(1)

    from roboflow import Roboflow

    rf = Roboflow(api_key=api_key)
    project = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)
    version = project.version(ROBOFLOW_VERSION)
    dataset = version.download("yolov8", location=str(DATASET_DIR))
    return dataset.location


def train():
    """Train YOLOv8x-pose on court keypoints."""
    # Check for dataset
    data_yaml = DATASET_DIR / "data.yaml"
    if not data_yaml.exists():
        print("Dataset not found. Downloading from Roboflow...")
        download_dataset()

    if not data_yaml.exists():
        print(f"ERROR: data.yaml not found at {data_yaml}")
        sys.exit(1)

    print(f"Training {MODEL} on court keypoint dataset")
    print(f"  Dataset: {data_yaml}")
    print(f"  Epochs: {EPOCHS}")
    print(f"  Image size: {IMGSZ}")
    print(f"  Batch size: {BATCH}")
    print(f"  Output: {OUTPUT_DIR}")

    model = YOLO(MODEL)
    results = model.train(
        task="pose",
        data=str(data_yaml),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        plots=True,
        project=str(OUTPUT_DIR.parent),
        name="court-detector",
        workers=0,  # Windows compatibility
    )

    # Copy best weights to expected location
    best_weights = Path(results.save_dir) / "weights" / "best.pt"
    if best_weights.exists():
        import shutil
        dest = OUTPUT_DIR / "best.pt"
        shutil.copy2(best_weights, dest)
        print(f"Best weights saved to {dest}")
    else:
        print("WARNING: best.pt not found in training output")

    return results


if __name__ == "__main__":
    train()
