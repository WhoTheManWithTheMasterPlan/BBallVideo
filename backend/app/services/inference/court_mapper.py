"""
Court mapping using OpenCV homography.
Maps pixel coordinates to normalized court coordinates.
"""

import cv2
import numpy as np


# Standard basketball court dimensions (in feet)
COURT_WIDTH = 50
COURT_LENGTH = 94


class CourtMapper:
    def __init__(self):
        self.homography_matrix: np.ndarray | None = None

    def calibrate(
        self,
        image_points: list[tuple[float, float]],
        court_points: list[tuple[float, float]],
    ):
        """
        Calibrate using known correspondences between image pixels and court coordinates.

        Args:
            image_points: At least 4 pixel coordinates of known court landmarks
            court_points: Corresponding real court coordinates (in feet)
        """
        src = np.array(image_points, dtype=np.float32)
        dst = np.array(court_points, dtype=np.float32)

        self.homography_matrix, _ = cv2.findHomography(src, dst, cv2.RANSAC)

    def pixel_to_court(self, x: float, y: float) -> tuple[float, float] | None:
        """Convert pixel coordinates to court coordinates."""
        if self.homography_matrix is None:
            return None

        point = np.array([[[x, y]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.homography_matrix)

        court_x = float(transformed[0][0][0])
        court_y = float(transformed[0][0][1])

        # Normalize to 0-1 range
        norm_x = court_x / COURT_LENGTH
        norm_y = court_y / COURT_WIDTH

        return (max(0, min(1, norm_x)), max(0, min(1, norm_y)))

    def save_calibration(self, path: str):
        """Save homography matrix to file."""
        if self.homography_matrix is not None:
            np.save(path, self.homography_matrix)

    def load_calibration(self, path: str):
        """Load homography matrix from file."""
        self.homography_matrix = np.load(path)
