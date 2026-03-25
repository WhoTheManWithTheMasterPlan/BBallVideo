"""
Jersey number OCR using PaddleOCR.
"""

import numpy as np
from paddleocr import PaddleOCR


class JerseyOCR:
    def __init__(self):
        self.ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

    def read_number(self, player_crop: np.ndarray) -> int | None:
        """
        Attempt to read a jersey number from a player crop.

        Returns the jersey number as int, or None if unreadable.
        """
        results = self.ocr.ocr(player_crop, cls=True)
        if not results or not results[0]:
            return None

        for line in results[0]:
            text = line[1][0].strip()
            confidence = line[1][1]

            # Jersey numbers are 0-99
            if text.isdigit() and 0 <= int(text) <= 99 and confidence > 0.5:
                return int(text)

        return None
