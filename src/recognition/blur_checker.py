import cv2
import numpy as np

def is_blurry(gray_frame: np.ndarray, threshold: float = 50.0) -> bool:
    """
    Check if a grayscale frame is blurry using the variance of Laplacian.
    """
    variance = cv2.Laplacian(gray_frame, cv2.CV_64F).var()
    return variance < threshold
