"""
Team classification using Fashion CLIP (zero-shot).
Classifies players into teams based on jersey color.
"""

import numpy as np
import open_clip
import torch
from PIL import Image


class TeamClassifier:
    def __init__(self):
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "hf-hub:Marqo/marqo-fashionCLIP"
        )
        self.tokenizer = open_clip.get_tokenizer("hf-hub:Marqo/marqo-fashionCLIP")
        self.model.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(self.device)

    def classify(
        self, player_crop: np.ndarray, team_descriptions: list[str]
    ) -> tuple[int, float]:
        """
        Classify a player crop into one of the teams.

        Args:
            player_crop: Cropped image of a player (numpy BGR)
            team_descriptions: e.g. ["person wearing white jersey", "person wearing dark blue jersey"]

        Returns:
            (team_index, confidence)
        """
        image = Image.fromarray(player_crop[:, :, ::-1])  # BGR -> RGB
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        text_tokens = self.tokenizer(team_descriptions).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            text_features = self.model.encode_text(text_tokens)

            image_features /= image_features.norm(dim=-1, keepdim=True)
            text_features /= text_features.norm(dim=-1, keepdim=True)

            similarity = (image_features @ text_features.T).softmax(dim=-1)
            team_idx = similarity.argmax().item()
            confidence = similarity[0, team_idx].item()

        return team_idx, confidence
