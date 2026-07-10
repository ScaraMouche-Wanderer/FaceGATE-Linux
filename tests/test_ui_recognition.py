import os
import sys
import unittest
from unittest.mock import patch
import cv2
import numpy as np


# Include src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from ui.auth_dialog import AuthDialog

class MockVideoCapture:
    def __init__(self, *args, **kwargs):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(current_dir, "test_face.png")
        self.img = cv2.imread(img_path)
        if self.img is None:
            raise RuntimeError(f"Could not load mock image from {img_path}")
        self.opened = True
        
    def isOpened(self):
        return self.opened
        
    def read(self):
        return True, self.img.copy()
        
    def set(self, propId, value):
        return True
        
    def get(self, propId):
        if propId == cv2.CAP_PROP_FRAME_WIDTH:
            return 640.0
        elif propId == cv2.CAP_PROP_FRAME_HEIGHT:
            return 480.0
        return 0.0
        
    def release(self):
        self.opened = False

class TestUiRecognition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create QApplication instance if not already running
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)
            
    @patch('recognition.matcher.cosine_similarity', return_value=0.85)
    @patch('recognition.matcher.load_embeddings', return_value={"test_user": np.zeros(512, dtype=np.float32)})
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_ui_flow(self, mock_vc, mock_load, mock_cos):
        print("=== Running UI Face Recognition Flow Test ===")
        
        # Instantiate the dialog in face mode
        dialog = AuthDialog("Test Terminal", mode="face", timeout_seconds=60)
        
        # Set a backup failure timer to force close the dialog if matching gets stuck
        failure_timer = QTimer()
        failure_timer.setSingleShot(True)
        failure_timer.timeout.connect(dialog.reject)
        failure_timer.start(30000) # 30 seconds limit
        
        result = dialog.exec()
        failure_timer.stop()
        
        print(f"Dialog result: {result}")
        print(f"Authenticated: {dialog.authenticated}")
        
        self.assertEqual(result, 1) # 1 is QDialog.DialogCode.Accepted
        self.assertTrue(dialog.authenticated)
        self.assertFalse(dialog.camera_error)
        self.assertFalse(dialog.timed_out)

    @patch('utils.systemd_manager.is_enabled', return_value=True)
    def test_settings_window_load(self, mock_systemd):
        print("=== Running UI Settings Window Load Test ===")
        from ui.settings_window import SettingsWindow
        from utils.config_loader import Config
        
        # Create a mock config
        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [
                {"id": "kitty", "name": "Kitty Terminal", "executable": "kitty", "desktop_name": "kitty.desktop", "icon": "kitty"}
            ],
            "app_monitor": {
                "on_auth_failure": "kill",
                "auth_timeout_seconds": 60
            },
            "behavior": {
                "uninstall_protection": True,
                "emergency_key": "<Control><Alt>k",
                "notify_on_auth": True,
                "autolock_on_idle": False,
                "autolock_on_idle_minutes": 10,
                "startup_delay_seconds": 0
            }
        }
        
        # Instantiate the settings window dialog
        dialog = SettingsWindow(config=mock_config)
        
        # Verify it populated correctly and no exceptions were thrown
        self.assertEqual(dialog.apps_table.rowCount(), 1)
        self.assertEqual(dialog.apps_table.item(0, 0).text(), "Kitty Terminal")
        self.assertEqual(dialog.apps_table.item(0, 1).text(), "kitty")

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_face_gate_application_sleep_relock(self, mock_dbus):
        print("=== Running Application Sleep/Lock Relocking Test ===")
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config
        
        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [
                {"id": "kitty", "name": "Kitty Terminal", "executable": "kitty", "desktop_name": "kitty.desktop", "icon": "kitty"}
            ],
            "app_monitor": {
                "on_auth_failure": "kill",
                "auth_timeout_seconds": 60
            },
            "behavior": {
                "uninstall_protection": True,
                "emergency_key": "<Control><Alt>k",
                "panic_key": "<Control><Alt>l",
                "notify_on_auth": True,
                "autolock_on_idle": False,
                "autolock_on_idle_minutes": 10,
                "startup_delay_seconds": 0,
                "lock_on_sleep_or_lock": True
            }
        }
        
        app = FaceGateApplication(config=mock_config)
        app.authorize_app("kitty.desktop")
        self.assertTrue(app.authorized_apps.get("kitty", False))
        
        # Trigger sleep signal handler
        app.handle_prepare_for_sleep(True)
        self.assertFalse(app.authorized_apps.get("kitty", False))
        
        # Re-authorize and trigger screensaver signal handler
        app.authorize_app("kitty.desktop")
        self.assertTrue(app.authorized_apps.get("kitty", False))
        
        app.handle_screensaver_active_changed(True)
        self.assertFalse(app.authorized_apps.get("kitty", False))

    def test_enrollment_wizard_load(self):
        print("=== Running Enrollment Wizard Load Test ===")
        from ui.enrollment_wizard import EnrollmentWizard
        wizard = EnrollmentWizard()
        self.assertIsNotNone(wizard.stack)

if __name__ == "__main__":
    unittest.main()
