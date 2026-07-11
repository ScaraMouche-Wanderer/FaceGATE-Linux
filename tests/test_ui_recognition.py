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
    @patch('database.embedding_store.load_embeddings',
           return_value={"test_user": np.zeros(512, dtype=np.float32)})
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    @patch('utils.config_loader.get_config')
    def test_face_recognition_accepts_matched_user(self, mock_get_config, mock_vc, mock_load, mock_cos):
        """Face mode dialog should accept after 3 consecutive match frames."""
        mock_config = MagicMock()
        from utils.config_loader import Config
        real_config = Config()
        def get_val(key, default=None):
            if key == "recognition.liveness_min_motion":
                return 0.0
            return real_config.get(key, default)
        mock_config.get.side_effect = get_val
        mock_get_config.return_value = mock_config

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

    @patch('utils.systemd_manager.is_active', return_value=True)
    @patch('utils.systemd_manager.restart', return_value=True)
    @patch('PySide6.QtWidgets.QMessageBox.information')
    @patch('utils.systemd_manager.is_enabled', return_value=True)
    def test_restart_daemon_systemd(self, mock_enabled, mock_info, mock_restart, mock_active):
        """If systemd service is active, restart_daemon should use systemd restart."""
        from ui.settings_window import SettingsWindow
        from utils.config_loader import Config
        
        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"on_auth_failure": "kill", "auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": True},
            "security": {"lock_settings_window": False},
        }
        window = SettingsWindow(config=mock_config)
        window.restart_daemon()
        mock_restart.assert_called_once()
        mock_info.assert_called_once()

    @patch('utils.systemd_manager.is_active', return_value=False)
    @patch('psutil.process_iter')
    @patch('subprocess.Popen')
    @patch('PySide6.QtWidgets.QMessageBox.information')
    @patch('utils.systemd_manager.is_enabled', return_value=True)
    def test_restart_daemon_manual(self, mock_enabled, mock_info, mock_popen, mock_iter, mock_active):
        """If systemd is not active, restart_daemon should terminate manual processes and spawn new monitor."""
        from ui.settings_window import SettingsWindow
        from utils.config_loader import Config
        
        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"on_auth_failure": "kill", "auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": True},
            "security": {"lock_settings_window": False},
        }
        window = SettingsWindow(config=mock_config)
        
        # Mock running processes
        mock_proc = MagicMock()
        mock_proc.info = {'cmdline': ['python', 'core/monitor_main.py', '--monitor']}
        mock_proc.pid = 9999
        mock_iter.return_value = [mock_proc]
        
        window.restart_daemon()
        
        mock_proc.terminate.assert_called_once()
        mock_popen.assert_called_once()
        mock_info.assert_called_once()


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
    @patch('ui.auth_dialog.AuthDialog')
    @patch('database.embedding_store.load_embeddings',
           return_value={"test_user": np.zeros(512)})
    def test_enrollment_requires_both_password_and_face(self, mock_load, mock_auth_dialog, mock_dbus):
        """Enrollment must require face verification when users exist."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": False},
        }

        mock_instance = MagicMock()
        mock_instance.exec.return_value = QDialog.DialogCode.Accepted
        mock_auth_dialog.return_value = mock_instance

        app = FaceGateApplication(config=mock_config)
        with patch('ui.enrollment_wizard.EnrollmentWizard.show') as mock_show:
            app.open_enrollment()
            mock_auth_dialog.assert_called_once()
            kwargs = mock_auth_dialog.call_args[1]
            self.assertEqual(kwargs.get("mode"), "face")
            mock_show.assert_called_once()

    @patch('core.monitor_main.register_dbus_service', return_value=True)
    @patch('ui.auth_dialog.AuthDialog')
    @patch('database.embedding_store.load_embeddings', return_value={})
    @patch('core.monitor_main.os.path.exists', return_value=False)
    def test_enrollment_skips_face_when_no_users(self, mock_exists, mock_load, mock_auth_dialog, mock_dbus):
        """Enrollment with no enrolled users must only require password (no face)."""
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "protected_apps": [],
            "app_monitor": {"auth_timeout_seconds": 60},
            "behavior": {"uninstall_protection": False},
        }

        mock_instance = MagicMock()
        mock_instance.exec.return_value = QDialog.DialogCode.Accepted
        mock_auth_dialog.return_value = mock_instance

        app = FaceGateApplication(config=mock_config)
        with patch('ui.enrollment_wizard.EnrollmentWizard.show') as mock_show:
            app.open_enrollment()
            mock_auth_dialog.assert_called_once()
            kwargs = mock_auth_dialog.call_args[1]
            self.assertEqual(kwargs.get("mode"), "password")
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


class TestIntruderSelfieGate(unittest.TestCase):
    """Tests for the intruder selfie gating behavior (Item 6b)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('ui.auth_dialog.AuthDialog.save_intruder_selfie')
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_no_selfie_on_clean_cancel(self, mock_vc, mock_save):
        """Clean cancel with no attempts must not capture an intruder selfie."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        dialog.reject()
        mock_save.assert_not_called()

    @patch('ui.auth_dialog.AuthDialog.save_intruder_selfie')
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_selfie_on_failed_attempts(self, mock_vc, mock_save):
        """Cancel after failed matches/ticks/timeouts must trigger intruder selfie."""
        from ui.auth_dialog import AuthDialog
        
        # Test Case 1: timed out
        dialog = AuthDialog("Test App", mode="face")
        dialog.timed_out = True
        dialog.reject()
        self.assertEqual(mock_save.call_count, 1)
        mock_save.reset_mock()

        # Test Case 2: close match attempts
        dialog = AuthDialog("Test App", mode="face")
        dialog.close_match_attempts = 1
        dialog.reject()
        self.assertEqual(mock_save.call_count, 1)
        mock_save.reset_mock()

        # Test Case 3: unknown face ticks
        dialog = AuthDialog("Test App", mode="face")
        dialog.unknown_face_ticks = 10
        dialog.reject()
        self.assertEqual(mock_save.call_count, 1)
        mock_save.reset_mock()

        # Test Case 4: failed password attempts
        dialog = AuthDialog("Test App", mode="password")
        dialog.failed_pwd_attempts = 1
        dialog.reject()
        self.assertEqual(mock_save.call_count, 1)


class TestAppPickerDialog(unittest.TestCase):
    """Tests for the AppPickerDialog component (Item 6d)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('ui.app_picker_dialog.get_installed_desktop_entries', return_value=[])
    def test_picker_does_not_close_on_empty_selection(self, mock_entries):
        """Clicking Add Protection with no app selected must show warning instead of closing."""
        from ui.app_picker_dialog import AppPickerDialog
        dialog = AppPickerDialog()
        
        with patch('PySide6.QtWidgets.QMessageBox.information') as mock_info:
            dialog.accept_selection()
            mock_info.assert_called_once()
            self.assertIsNone(dialog.selected_app)
            self.assertEqual(dialog.result(), 0)


class TestChangePasswordDialog(unittest.TestCase):
    """Tests for the ChangePasswordDialog component (Item 6c)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('database.embedding_store.read_envelope_file', return_value=None)
    def test_dialog_no_current_password_on_first_run(self, mock_envelope):
        """If no master password is set, the dialog should not ask for the current one."""
        from ui.settings_window import ChangePasswordDialog
        dialog = ChangePasswordDialog()
        self.assertFalse(dialog.has_current)
        self.assertIsNone(dialog.current_input)

    @patch('database.embedding_store.read_envelope_file', return_value={"salt": "dummy"})
    def test_dialog_has_current_password_field(self, mock_envelope):
        """If a master password exists, it must ask for the current one."""
        from ui.settings_window import ChangePasswordDialog
        dialog = ChangePasswordDialog()
        self.assertTrue(dialog.has_current)
        self.assertIsNotNone(dialog.current_input)

    @patch('database.embedding_store.read_envelope_file', return_value={"salt": "dummy"})
    @patch('security.credential_store.update_master_password')
    def test_change_password_success(self, mock_update, mock_envelope):
        """Entering correct inputs must call update_master_password and accept."""
        from ui.settings_window import ChangePasswordDialog
        dialog = ChangePasswordDialog()
        dialog.current_input.setText("current123")
        dialog.new_input.setText("newpassword123")
        dialog.confirm_input.setText("newpassword123")
        dialog.handle_change()
        mock_update.assert_called_once_with("current123", "newpassword123")
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)


class TestThemeDynamicUpdating(unittest.TestCase):
    """Tests for dynamic theme updates and CustomTitleBar (Item 7)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    @patch('database.embedding_store.load_embeddings', return_value={})
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_auth_dialog_enrollment_wizard_dynamic_theme(self, mock_vc, mock_load):
        """AuthDialog and EnrollmentWizard must support apply_theme_dynamically."""
        from ui.auth_dialog import AuthDialog
        from ui.enrollment_wizard import EnrollmentWizard
        from utils.config_loader import get_config
        config = get_config()
        
        # Test AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        dialog.apply_theme_dynamically()
        # Verify title bar style updated
        self.assertIsNotNone(dialog.title_bar.title_lbl.styleSheet())
        
        # Test EnrollmentWizard
        wizard = EnrollmentWizard()
        wizard.apply_theme_dynamically()
        self.assertIsNotNone(wizard.title_bar.title_lbl.styleSheet())

    def test_settings_window_dynamic_theme(self):
        """SettingsWindow must update registered themed labels dynamically on theme switch."""
        from ui.settings_window import SettingsWindow
        from ui.theme import get_colors
        from utils.config_loader import get_config
        
        # Instantiate SettingsWindow
        window = SettingsWindow()
        
        # 1. Force light theme and apply theme
        config = get_config()
        config.set("behavior.theme", "light")
        config.save()
        window.apply_theme_dynamically()
        
        # Get light colors
        c_light = get_colors()
        light_color = c_light["TEXT_PRIMARY"]
        
        # Sample one of the heading labels
        sampled_label = None
        for label, color_key in window._themed_labels:
            if color_key == "TEXT_PRIMARY" and label.property("heading_size") == 20:
                sampled_label = label
                break
                
        self.assertIsNotNone(sampled_label, "A heading label of size 20 should be registered.")
        
        # Assert label has light mode color in its style sheet
        self.assertIn(light_color.lower(), sampled_label.styleSheet().lower())
        
        # 2. Simulate theme switch to dark
        config.set("behavior.theme", "dark")
        config.save()
        window.apply_theme_dynamically()
        
        # Get dark colors
        c_dark = get_colors()
        dark_color = c_dark["TEXT_PRIMARY"]
        
        # Assert label has dark mode color in its style sheet now
        self.assertIn(dark_color.lower(), sampled_label.styleSheet().lower())
        self.assertNotIn(light_color.lower(), sampled_label.styleSheet().lower())

    def test_get_sidebar_qss_uses_is_dark(self):
        """get_sidebar_qss must detect dark mode via IS_DARK key."""
        from ui.theme import get_sidebar_qss, get_colors
        
        c_dark = get_colors().copy()
        c_dark["IS_DARK"] = True
        
        c_light = get_colors().copy()
        c_light["IS_DARK"] = False
        
        qss_dark = get_sidebar_qss(c_dark)
        qss_light = get_sidebar_qss(c_light)
        
        self.assertIn("#191624", qss_dark)
        self.assertIn("#ede9fe", qss_light)


if __name__ == "__main__":
    unittest.main()
