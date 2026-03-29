"""
Player Re-Identification using OSNet.
Generates appearance embeddings for matching players across frames and to roster photos.
"""

import io
import logging
from dataclasses import dataclass

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

logger = logging.getLogger(__name__)

# OSNet transform: standard ReID preprocessing
REID_TRANSFORM = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


@dataclass
class ReIDMatch:
    player_id: str  # roster player UUID
    name: str
    jersey_number: int
    team_name: str
    confidence: float  # cosine similarity score


class ReIDExtractor:
    """Extracts appearance embeddings for player re-identification.

    Model priority: resnet50.a2_in1k (via timm) > ResNet18 (torchvision fallback).
    ResNet50 produces 2048-dim embeddings with much better discrimination than ResNet18's 512-dim.
    """

    def __init__(self, model_name: str = "resnet50.a2_in1k"):
        try:
            import timm
            self.model = timm.create_model(model_name, pretrained=True, num_classes=0)
            logger.info(f"ReID model loaded: {model_name} via timm")
        except (ImportError, RuntimeError) as e:
            logger.warning(f"{model_name} unavailable ({e}), falling back to ResNet18")
            from torchvision.models import resnet18, ResNet18_Weights
            model = resnet18(weights=ResNet18_Weights.DEFAULT)
            self.model = torch.nn.Sequential(*list(model.children())[:-1], torch.nn.Flatten())

        self.model.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(self.device)

    def _preprocess(self, image: np.ndarray) -> torch.Tensor:
        """Convert BGR numpy array to preprocessed tensor."""
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        return REID_TRANSFORM(pil_image).unsqueeze(0).to(self.device)

    def extract_embedding(self, crop: np.ndarray) -> np.ndarray:
        """Extract a normalized embedding vector from a player crop (BGR numpy)."""
        tensor = self._preprocess(crop)
        with torch.no_grad():
            embedding = self.model(tensor)
            embedding = F.normalize(embedding, dim=1)
        return embedding.cpu().numpy().flatten()

    def extract_from_bytes(self, image_bytes: bytes) -> bytes | None:
        """Extract embedding from raw image bytes (e.g. uploaded photo). Returns embedding as bytes."""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                return None

            # Detect person in the image and crop
            crop = self._find_person_crop(image)
            if crop is None:
                crop = image  # Use full image if no person detected

            embedding = self.extract_embedding(crop)
            return embedding.tobytes()
        except Exception as e:
            logger.error(f"Failed to extract embedding from photo: {e}")
            return None

    def extract_from_team_photo(self, image_bytes: bytes) -> list[dict]:
        """
        Extract player crops and embeddings from a team photo.
        Returns list of {crop_bytes, embedding, jersey_number}.
        """
        from app.services.inference.detector import PlayerBallDetector
        from app.services.inference.ocr import JerseyOCR

        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            return []

        # Detect all people in the photo
        detector = PlayerBallDetector()
        detections = detector.detect_frame(image, frame_idx=0)

        ocr = JerseyOCR()
        results = []

        for det in detections:
            if det.class_name != "person":
                continue

            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # Extract embedding
            embedding = self.extract_embedding(crop)

            # Try to read jersey number
            jersey_number = ocr.read_number(crop)

            # Encode crop as JPEG bytes
            _, crop_encoded = cv2.imencode(".jpg", crop)

            results.append({
                "embedding": embedding.tobytes(),
                "jersey_number": jersey_number,
                "crop_bytes": crop_encoded.tobytes(),
                "bbox": (x1, y1, x2, y2),
            })

        logger.info(f"Team photo: detected {len(results)} players, "
                     f"{sum(1 for r in results if r['jersey_number'] is not None)} with jersey numbers")
        return results

    def _find_person_crop(self, image: np.ndarray) -> np.ndarray | None:
        """Find and crop the largest person in an image."""
        from app.services.inference.detector import PlayerBallDetector

        detector = PlayerBallDetector()
        detections = detector.detect_frame(image, frame_idx=0)

        person_dets = [d for d in detections if d.class_name == "person"]
        if not person_dets:
            return None

        # Take the largest bounding box (likely the main subject)
        best = max(person_dets, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))
        x1, y1, x2, y2 = [int(v) for v in best.bbox]
        return image[y1:y2, x1:x2]


class ReIDMatcher:
    """Matches detected players to known roster players using embedding similarity."""

    def __init__(self, match_threshold: float = 0.55):
        self.match_threshold = match_threshold
        self._score_log_count = 0  # throttle debug logging
        self.roster_embeddings: dict[str, np.ndarray] = {}  # player_id -> embedding
        self.roster_info: dict[str, dict] = {}  # player_id -> {name, jersey_number, team_name}

    def load_roster(self, players: list[dict]):
        """
        Load roster player embeddings for matching.

        Args:
            players: list of {id, name, jersey_number, team_name, reid_embedding (bytes)}
        """
        self.roster_embeddings.clear()
        self.roster_info.clear()

        for p in players:
            if p.get("reid_embedding"):
                embedding = np.frombuffer(p["reid_embedding"], dtype=np.float32)
                self.roster_embeddings[p["id"]] = embedding
                self.roster_info[p["id"]] = {
                    "name": p["name"],
                    "jersey_number": p["jersey_number"],
                    "team_name": p["team_name"],
                }

        logger.info(f"Loaded {len(self.roster_embeddings)} player embeddings for matching")

    def load_profile(self, embeddings: list[np.ndarray]):
        """
        Load target profile embeddings for matching.
        Used in player-centric mode — just checks if a detected player IS the target.

        Args:
            embeddings: list of numpy embedding arrays from profile photos
        """
        self.roster_embeddings.clear()
        self.roster_info.clear()

        for i, emb in enumerate(embeddings):
            key = f"profile_{i}"
            self.roster_embeddings[key] = emb
            self.roster_info[key] = {
                "name": "target",
                "jersey_number": None,
                "team_name": None,
            }

        logger.info(f"Loaded {len(self.roster_embeddings)} profile embeddings for target matching")

    def match(self, query_embedding: np.ndarray) -> ReIDMatch | None:
        """
        Find the best matching player for a query embedding.

        Returns ReIDMatch if confidence > threshold, else None.
        """
        if not self.roster_embeddings:
            return None

        best_id = None
        best_score = -1.0

        for player_id, ref_embedding in self.roster_embeddings.items():
            score = float(np.dot(query_embedding, ref_embedding))
            if score > best_score:
                best_score = score
                best_id = player_id

        # Log score distribution periodically (every 50th query) to calibrate threshold
        self._score_log_count += 1
        if self._score_log_count <= 20 or self._score_log_count % 50 == 0:
            logger.info(f"ReID score: {best_score:.3f} (threshold={self.match_threshold}, query #{self._score_log_count})")

        if best_id is None or best_score < self.match_threshold:
            return None

        info = self.roster_info[best_id]
        return ReIDMatch(
            player_id=best_id,
            name=info["name"],
            jersey_number=info["jersey_number"],
            team_name=info["team_name"],
            confidence=best_score,
        )
