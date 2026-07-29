import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QTimer

# Setup PySide6 app
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

class MockVideoCaptureStatic:
    def __init__(self, *args, **kwargs):
        self.opened = True
    def isOpened(self): return self.opened
    def read(self):
        # Return a black frame
        return True, np.zeros((480, 640, 3), dtype=np.uint8)
    def set(self, propId, value): return True
    def get(self, propId): return 640.0 if propId == 3 else 480.0
    def release(self): self.opened = False

class MockDetectorStatic:
    def __init__(self, *args, **kwargs):
        pass
    def detect_faces(self, frame):
        # Always return a static face at the exact same location
        return [{
            'bbox': [100, 100, 200, 200],
            'embedding': np.zeros(512, dtype=np.float32),
            'kps': np.zeros((5, 2))
        }]

class MockDetectorMoving:
    def __init__(self, *args, **kwargs):
        self.frame_count = 0
    def detect_faces(self, frame):
        # Shift face slightly in each frame to simulate micro-motion
        offset = self.frame_count * 5 # 5 pixels movement per frame
        self.frame_count += 1
        return [{
            'bbox': [100 + offset, 100, 200 + offset, 200],
            'embedding': np.zeros(512, dtype=np.float32),
            'kps': np.zeros((5, 2))
        }]

@patch('recognition.matcher.cosine_similarity', return_value=0.85)
@patch('database.embedding_store.load_embeddings', return_value={"test_user": np.zeros(512, dtype=np.float32)})
@patch('cv2.VideoCapture', side_effect=MockVideoCaptureStatic)
@patch('utils.config_loader.get_config')
def test_liveness_flags_zero_motion(mock_get_config, mock_vc, mock_load, mock_cos):
    """Confirm that a perfectly static sequence (zero-motion) fails the liveness check."""
    from ui.auth_dialog import AuthDialog
    
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key, default=None: 0.5 if key == "recognition.liveness_min_motion" else default
    mock_get_config.return_value = mock_config
    
    # We patch the Detector inside AuthDialog so it returns static boxes
    with patch('recognition.detector.Detector', side_effect=MockDetectorStatic):
        dialog = AuthDialog("Test Terminal", mode="face", timeout_seconds=2)
        
        # Close after 1.5 seconds if it hasn't finished
        QTimer.singleShot(1500, dialog.reject)
        result = dialog.exec()
        
        # It must not be accepted because motion (0.0) is < threshold (0.5)
        assert result == QDialog.DialogCode.Rejected
        assert not dialog.authenticated

@patch('recognition.blur_checker.is_blurry', return_value=False)
@patch('recognition.matcher.cosine_similarity', return_value=0.85)
@patch('database.embedding_store.load_embeddings', return_value={"test_user": np.zeros(512, dtype=np.float32)})
@patch('cv2.VideoCapture', side_effect=MockVideoCaptureStatic)
@patch('utils.config_loader.get_config')
def test_liveness_accepts_moving_sequence(mock_get_config, mock_vc, mock_load, mock_cos, mock_blur):
    """Confirm that a sequence with micro-motion passes the liveness check."""
    from ui.auth_dialog import AuthDialog
    
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key, default=None: 0.5 if key == "recognition.liveness_min_motion" else default
    mock_get_config.return_value = mock_config
    
    # We patch the Detector inside AuthDialog so it returns moving boxes
    with patch('recognition.detector.Detector', side_effect=MockDetectorMoving):
        dialog = AuthDialog("Test Terminal", mode="face", timeout_seconds=5)
        
        # Close after 4 seconds as a fallback
        QTimer.singleShot(4000, dialog.reject)
        result = dialog.exec()
        
        # It must be accepted because motion is > threshold (0.5)
        assert result == QDialog.DialogCode.Accepted
        assert dialog.authenticated
        assert dialog.matched_user == "test_user"

@patch('recognition.blur_checker.is_blurry', return_value=False)
@patch('recognition.matcher.cosine_similarity', return_value=0.98)
@patch('database.embedding_store.load_embeddings', return_value={"test_user": np.zeros(512, dtype=np.float32)})
@patch('cv2.VideoCapture', side_effect=MockVideoCaptureStatic)
@patch('utils.config_loader.get_config')
def test_liveness_requires_motion_even_for_high_confidence_match(mock_get_config, mock_vc, mock_load, mock_cos, mock_blur):
    """High-confidence match (0.98) must NOT bypass the motion/liveness check if static."""
    from ui.auth_dialog import AuthDialog
    
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key, default=None: 0.5 if key == "recognition.liveness_min_motion" else default
    mock_get_config.return_value = mock_config
    
    with patch('recognition.detector.Detector', side_effect=MockDetectorStatic):
        dialog = AuthDialog("Test Terminal", mode="face", timeout_seconds=2)
        QTimer.singleShot(1500, dialog.reject)
        result = dialog.exec()
        
        assert result == QDialog.DialogCode.Rejected
        assert not dialog.authenticated
