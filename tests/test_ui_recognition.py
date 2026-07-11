"""
Tests for the FaceGate UI components and application lifecycle.
Covers: AuthDialog, SettingsWindow loading, enrollment flow,
sleep/lock relocking, and configuration management.

Updated to match post-security-audit codebase:
- No hardcoded password auto-init
- EmergencyKill requires authentication
- Config.save() writes to user directory
- Cached key uses bytearray
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QTimer


class MockVideoCapture:
    """Mocks cv2.VideoCapture for headless face recognition tests."""

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


class TestAuthDialog(unittest.TestCase):
    """Tests for the authentication dialog."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('recognition.matcher.cosine_similarity', return_value=0.85)
    @patch('recognition.matcher.load_embeddings',
           return_value={"test_user": np.zeros(512, dtype=np.float32)})
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_accepts_matched_user(self, mock_vc, mock_load, mock_cos):
        """Face mode dialog should accept after 3 consecutive match frames."""
        from ui.auth_dialog import AuthDialog

        dialog = AuthDialog("Test Terminal", mode="face", timeout_seconds=60)

        failure_timer = QTimer()
        failure_timer.setSingleShot(True)
        failure_timer.timeout.connect(dialog.reject)
        failure_timer.start(30000)

        result = dialog.exec()
        failure_timer.stop()

        self.assertEqual(result, QDialog.DialogCode.Accepted)
        self.assertTrue(dialog.authenticated)
        self.assertFalse(dialog.camera_error)
        self.assertFalse(dialog.timed_out)
        self.assertEqual(dialog.matched_user, "test_user")
        self.assertIsNotNone(dialog.final_score)

    def test_password_mode_lockout_after_3_failures(self):
        """Password dialog should impose lockout after 3 failed attempts."""
        from ui.auth_dialog import AuthDialog

        # Reset class-level state
        AuthDialog.failed_attempts_count = 0
        AuthDialog.lockout_until = 0.0

        dialog = AuthDialog("Test App", mode="password")

        # Simulate 3 failed password attempts
        with patch('security.credential_store.verify_password', return_value=False):
            for _ in range(3):
                dialog.password_input.setText("wrong")
                dialog.handle_unlock()

        self.assertEqual(AuthDialog.failed_attempts_count, 3)
        self.assertGreater(AuthDialog.lockout_until, 0.0)

        # Clean up class state
        AuthDialog.failed_attempts_count = 0
        AuthDialog.lockout_until = 0.0


class TestSettingsWindow(unittest.TestCase):
    """Tests for the Settings window component."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('utils.systemd_manager.is_enabled', return_value=True)
    def test_settings_loads_protected_apps(self, mock_systemd):
        """Settings window should populate the apps table from config."""
        from ui.settings_window import SettingsWindow
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [
                {"id": "kitty", "name": "Kitty Terminal",
                 "executable": "kitty", "desktop_name": "kitty.desktop", "icon": "kitty"}
            ],
            "app_monitor": {"on_auth_failure": "kill", "auth_timeout_seconds": 60},
            "behavior": {
                "uninstall_protection": True,
                "emergency_key": "<Control><Alt>k",
                "panic_key": "<Control><Alt>l",
                "notify_on_auth": True,
                "autolock_on_idle": False,
                "autolock_on_idle_minutes": 10,
                "startup_delay_seconds": 0,
                "lock_on_sleep_or_lock": True,
            },
            "security": {"lock_settings_window": True},
        }

        dialog = SettingsWindow(config=mock_config)

        self.assertEqual(dialog.apps_table.rowCount(), 1)
        self.assertEqual(dialog.apps_table.item(0, 0).text(), "Kitty Terminal")
        self.assertEqual(dialog.apps_table.item(0, 1).text(), "kitty\n(kitty.desktop)")


class TestConfigSavePath(unittest.TestCase):
    """Tests that config saves to user directory, not source tree (M2 fix)."""

    def test_save_writes_to_user_config_dir(self):
        """Config.save() must write to ~/.config/facegate/config.yaml."""
        import inspect
        from utils.config_loader import Config
        source = inspect.getsource(Config.save)
        assert "~/.config/facegate/config.yaml" in source, \
            "Config.save() must write to user config directory"
        assert "default.yaml" not in source, \
            "Config.save() must NOT write to source-tree default.yaml"


class TestApplicationLifecycle(unittest.TestCase):
    """Tests for the FaceGateApplication event handlers."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_sleep_relocks_all_apps(self, mock_dbus):
        """PrepareForSleep(true) must relock all authorized apps."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [
                {"id": "kitty", "name": "Kitty Terminal",
                 "executable": "kitty", "desktop_name": "kitty.desktop"}
            ],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {
                "uninstall_protection": False,
                "lock_on_sleep_or_lock": True,
            },
        }

        app = FaceGateApplication(config=mock_config)
        app.authorize_app("kitty.desktop")
        self.assertTrue(app.authorized_apps.get("kitty", False))

        # Trigger sleep handler
        app.handle_prepare_for_sleep(True)
        self.assertFalse(app.authorized_apps.get("kitty", False))

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_screensaver_relocks_all_apps(self, mock_dbus):
        """ScreenSaver ActiveChanged(true) must relock all authorized apps."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [
                {"id": "kitty", "name": "Kitty Terminal",
                 "executable": "kitty", "desktop_name": "kitty.desktop"}
            ],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {
                "uninstall_protection": False,
                "lock_on_sleep_or_lock": True,
            },
        }

        app = FaceGateApplication(config=mock_config)
        app.authorize_app("kitty.desktop")
        self.assertTrue(app.authorized_apps.get("kitty", False))

        # Trigger screensaver handler
        app.handle_screensaver_active_changed(True)
        self.assertFalse(app.authorized_apps.get("kitty", False))

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_quit_clears_cached_key(self, mock_dbus):
        """quit_app() must clear the cached encryption key from memory."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config
        from database.embedding_store import set_cached_key, get_cached_key

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": False},
        }

        app = FaceGateApplication(config=mock_config)
        set_cached_key(os.urandom(32))
        self.assertIsNotNone(get_cached_key())

        # Quit (bypass protection since it's disabled in config)
        with patch('PySide6.QtWidgets.QApplication.quit'):
            with patch.object(app, 'get_protected_apps', return_value=[]):
                app.quit_app(bypass_protection=True)

        self.assertIsNone(get_cached_key())


class TestEnrollmentFlow(unittest.TestCase):
    """Tests for the enrollment flow's authentication gates."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    @patch('ui.auth_dialog.AuthDialog.exec', return_value=QDialog.DialogCode.Accepted)
    @patch('database.embedding_store.load_embeddings',
           return_value={"test_user": np.zeros(512)})
    def test_enrollment_requires_both_password_and_face(self, mock_load, mock_exec, mock_dbus):
        """Enrollment must require password + face verification when users exist."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": False},
        }

        app = FaceGateApplication(config=mock_config)
        with patch('ui.enrollment_wizard.EnrollmentWizard.show') as mock_show:
            app.open_enrollment()
            # Password dialog + face dialog = 2 calls
            self.assertEqual(mock_exec.call_count, 2)
            mock_show.assert_called_once()

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    @patch('ui.auth_dialog.AuthDialog.exec', return_value=QDialog.DialogCode.Accepted)
    @patch('database.embedding_store.load_embeddings', return_value={})
    def test_enrollment_skips_face_when_no_users(self, mock_load, mock_exec, mock_dbus):
        """Enrollment with no enrolled users must only require password (no face)."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": False},
        }

        app = FaceGateApplication(config=mock_config)
        with patch('ui.enrollment_wizard.EnrollmentWizard.show') as mock_show:
            app.open_enrollment()
            # Only password dialog = 1 call
            self.assertEqual(mock_exec.call_count, 1)
            mock_show.assert_called_once()


class TestEnrollmentWizard(unittest.TestCase):
    """Tests for the enrollment wizard UI component."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_wizard_loads_without_errors(self):
        """EnrollmentWizard must instantiate without exceptions."""
        from ui.enrollment_wizard import EnrollmentWizard
        wizard = EnrollmentWizard()
        self.assertIsNotNone(wizard.stack)


if __name__ == "__main__":
    unittest.main()
