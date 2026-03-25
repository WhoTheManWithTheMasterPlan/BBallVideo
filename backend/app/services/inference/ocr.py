"""
Jersey number OCR using EasyOCR.
"""

import numpy as np
import easyocr


class JerseyOCR:
    def __init__(self):
        self.reader = easyocr.Reader(["en"], gpu=True, verbose=False)

    def read_number(self, player_crop: np.ndarray) -> int | None:
        """
        Attempt to read a jersey number from a player crop.

        Returns the jersey number as int, or None if unreadable.
        """
        results = self.reader.readtext(player_crop, allowlist="0123456789")
        if not results:
            return None

        for bbox, text, confidence in results:
            text = text.strip()
            # Jersey numbers are 0-99
            if text.isdigit() and 0 <= int(text) <= 99 and confidence > 0.5:
                return int(text)

        return None
