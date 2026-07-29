import cv2
import numpy as np

def is_blurry(gray_frame: np.ndarray, threshold: float = 12.0) -> bool:
    """
    Check if a grayscale frame is severely blurry using the variance of Laplacian.
    Lowered threshold (12.0) prevents discarding normal indoor webcam frames.
    """
    variance = cv2.Laplacian(gray_frame, cv2.CV_64F).var()
    return variance < threshold
