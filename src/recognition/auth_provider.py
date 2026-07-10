from abc import ABC, abstractmethod
import logging
import numpy as np
from recognition.matcher import match_face

class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, app_identifier: str) -> bool:
        pass

class FaceRecognitionProvider(AuthProvider):
    def __init__(self, detector):
        self.detector = detector

    def authenticate(self, app_identifier: str) -> bool:
        """
        Runs authentication logic on a single face.
        This is a helper designed to be called when a face frame is captured.
        """
        pass
