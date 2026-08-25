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
        self._frame_count = 0

    def isOpened(self):
        return self.opened

    def read(self):
        # Apply a small, alternating frame-to-frame translation to simulate
        # the natural hand/head micro-jitter present in any real live camera
        # feed. Returning the byte-identical frame every call (as before)
        # represents a printed photo/screen held perfectly still - exactly
        # the presentation attack the liveness check in auth_dialog.py is
        # meant to reject - so it is not a realistic stand-in for a live
        # subject and would defeat the very check it should be exercising.
        self._frame_count += 1
        offset = 3 if (self._frame_count % 2 == 0) else -3
        h, w = self.img.shape[:2]
        translation_matrix = np.float32([[1, 0, offset], [0, 1, 0]])
        jittered = cv2.warpAffine(
            self.img, translation_matrix, (w, h), borderMode=cv2.BORDER_REPLICATE
        )
        return True, jittered

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
        """Face mode dialog should accept after consecutive match frames with micro-motion."""
        from utils.config_loader import Config
        mock_get_config.return_value = Config()

        from ui.auth_dialog import AuthDialog

        with patch('recognition.detector.Detector', side_effect=MockDetectorMoving):
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

    @patch('database.embedding_store.load_embeddings',
           return_value={"test_user": np.zeros(512, dtype=np.float32)})
    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_high_confidence_immediate_auth(self, mock_vc, mock_load):
        """High-confidence match (score >= threshold + 0.12) authenticates immediately with motion."""
        from ui.auth_dialog import AuthDialog
        from utils.config_loader import Config

        with patch('utils.config_loader.get_config', return_value=Config()):
            dialog = AuthDialog("Test Terminal", mode="face")
            dialog.enrolled_embeddings = {"test_user": np.zeros(512, dtype=np.float32)}

            dummy_frame = np.ones((270, 360, 3), dtype=np.uint8) * 128
            faces = [{
                'bbox': [100, 100, 200, 200],
                'embedding': np.zeros(512, dtype=np.float32),
                'kps': np.zeros((5, 2))
            }]

            with patch('recognition.matcher.match_face', return_value=("test_user", 0.90)):
                with patch('recognition.blur_checker.is_blurry', return_value=False):
                    dialog.warmup_frames_left = 0
                    # First frame: records centroid 1
                    dialog.handle_detection_result(faces, dummy_frame)

                    # Second frame: shifted centroid 2 to satisfy motion check
                    faces_moved = [{
                        'bbox': [105, 105, 205, 205],
                        'embedding': np.zeros(512, dtype=np.float32),
                        'kps': np.zeros((5, 2))
                    }]
                    dialog.handle_detection_result(faces_moved, dummy_frame)

            self.assertTrue(dialog.authenticated)
            self.assertEqual(dialog.matched_user, "test_user")

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_unknown_face_ticks_fallback(self, mock_vc):
        """Unknown face scan for 90 ticks automatically triggers password fallback."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        dialog.enrolled_embeddings = {"test_user": np.zeros(512, dtype=np.float32)}
        dialog.warmup_frames_left = 0

        dummy_frame = np.ones((270, 360, 3), dtype=np.uint8) * 128
        faces = [{
            'bbox': [100, 100, 200, 200],
            'embedding': np.random.randn(512).astype(np.float32),
            'kps': np.zeros((5, 2))
        }]

        with patch('recognition.matcher.match_face', return_value=(None, 0.10)):
            with patch('recognition.blur_checker.is_blurry', return_value=False):
                for _ in range(89):
                    dialog.handle_detection_result(faces, dummy_frame)
                self.assertFalse(dialog.fallback_to_password)
                self.assertEqual(dialog.unknown_face_ticks, 89)

                # 90th tick triggers fallback
                dialog.handle_detection_result(faces, dummy_frame)
                self.assertTrue(dialog.fallback_to_password)
                self.assertEqual(dialog.stack.currentIndex(), 1)

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_close_mismatch_ambiguity_fallback(self, mock_vc):
        """Close mismatches (near threshold) update status and trigger password fallback after 3 attempts."""
        from ui.auth_dialog import AuthDialog
        from utils.config_loader import Config
        cfg = Config()

        with patch('utils.config_loader.get_config', return_value=cfg):
            dialog = AuthDialog("Test App", mode="face")
            dialog.enrolled_embeddings = {"test_user": np.zeros(512, dtype=np.float32)}
            dialog.warmup_frames_left = 0

            dummy_frame = np.ones((270, 360, 3), dtype=np.uint8) * 128
            faces = [{
                'bbox': [100, 100, 200, 200],
                'embedding': np.zeros(512, dtype=np.float32),
                'kps': np.zeros((5, 2))
            }]

            # threshold = 0.52, margin = 0.03. Score 0.50 is >= (0.52 - 0.03) = 0.49
            with patch('recognition.matcher.match_face', return_value=(None, 0.50)):
                with patch('recognition.blur_checker.is_blurry', return_value=False):
                    dialog.handle_detection_result(faces, dummy_frame)
                    self.assertIn("Almost — try better lighting", dialog.status_label.text())
                    self.assertEqual(dialog.close_match_attempts, 1)

                    dialog.handle_detection_result(faces, dummy_frame)
                    self.assertEqual(dialog.close_match_attempts, 2)

                    dialog.handle_detection_result(faces, dummy_frame)
                    self.assertEqual(dialog.close_match_attempts, 3)
                    self.assertTrue(dialog.fallback_to_password)
                    self.assertEqual(dialog.stack.currentIndex(), 1)

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_camera_error_triggers_fallback(self, mock_vc):
        """Camera loading error sets camera_error flag and displays error UI before password mode."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")

        dialog.on_detector_load_error("Failed to open camera /dev/video0")
        self.assertTrue(dialog.camera_error)
        self.assertEqual(dialog.camera_error_msg, "Failed to open camera /dev/video0")
        self.assertIn("Camera Error", dialog.status_label.text())

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    @patch('database.embedding_store.get_cached_key', return_value=b'12345678901234567890123456789012')
    @patch('database.embedding_store.load_embeddings', return_value={})
    def test_face_recognition_no_enrolled_profiles_auto_fallback(self, mock_load, mock_key, mock_vc):
        """No enrolled facial profiles automatically switches AuthDialog to password mode."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        mock_detector = MagicMock()
        dialog.on_detector_loaded(mock_detector)

        self.assertTrue(dialog.fallback_to_password)
        self.assertIn("No facial profiles enrolled yet", dialog.sub_label.text())
        self.assertEqual(dialog.stack.currentIndex(), 1)

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_dark_frame_warning_message(self, mock_vc):
        """Dark camera frame (mean < 15.0) sets low-light warning on status label."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        dialog.detector = MagicMock()

        dark_frame = np.zeros((270, 360, 3), dtype=np.uint8) # mean is 0.0
        dialog.handle_frame(dark_frame)
        self.assertIn("Camera is dark", dialog.status_label.text())

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_blurry_frame_filtering(self, mock_vc):
        """Blurry frame skips evaluation, leaving success count and ticks untouched."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        dialog.warmup_frames_left = 0

        dummy_frame = np.ones((270, 360, 3), dtype=np.uint8) * 128
        faces = [{'bbox': [10, 10, 50, 50], 'embedding': np.zeros(512), 'kps': np.zeros((5, 2))}]

        with patch('recognition.blur_checker.is_blurry', return_value=True):
            dialog.handle_detection_result(faces, dummy_frame)
            self.assertEqual(dialog.success_count, 0)
            self.assertEqual(dialog.unknown_face_ticks, 0)

    @patch('cv2.VideoCapture', side_effect=MockVideoCapture)
    def test_face_recognition_multi_face_detection_matching(self, mock_vc):
        """Multiple faces in frame correctly identify enrolled user while processing all reticles."""
        from ui.auth_dialog import AuthDialog
        dialog = AuthDialog("Test App", mode="face")
        dialog.enrolled_embeddings = {"admin_user": np.zeros(512, dtype=np.float32)}
        dialog.warmup_frames_left = 0

        dummy_frame = np.ones((270, 360, 3), dtype=np.uint8) * 128
        faces = [
            {'bbox': [10, 10, 50, 50], 'embedding': np.ones(512), 'kps': np.zeros((5, 2))},
            {'bbox': [100, 100, 200, 200], 'embedding': np.zeros(512), 'kps': np.zeros((5, 2))}
        ]

        def mock_matcher(emb, enrolled):
            if np.array_equal(emb, np.zeros(512)):
                return ("admin_user", 0.92)
            return (None, 0.15)

        with patch('recognition.matcher.match_face', side_effect=mock_matcher):
            with patch('recognition.blur_checker.is_blurry', return_value=False):
                dialog.handle_detection_result(faces, dummy_frame)

        self.assertEqual(dialog.success_count, 1)

    def test_password_mode_lockout_after_3_failures(self):
        """Password dialog should impose lockout after 3 failed attempts (tracked per app)."""
        import tempfile
        from ui.auth_dialog import AuthDialog
        from security.lockout_manager import reset_lockout, is_locked_out

        with tempfile.TemporaryDirectory() as tmp_dir:
            lockout_path = os.path.join(tmp_dir, "lockout.json")
            with patch("security.lockout_manager.LOCKOUT_FILE", lockout_path):
                app_name = "Test App"
                reset_lockout(app_name)

                dialog = AuthDialog(app_name, mode="password")

                # Simulate 3 failed password attempts
                with patch('security.credential_store.verify_password', return_value=False):
                    for _ in range(3):
                        dialog.password_input.setText("wrong")
                        dialog.handle_unlock()

                is_locked, remaining = is_locked_out(app_name)
                self.assertTrue(is_locked)
                self.assertGreater(remaining, 0.0)

                reset_lockout(app_name)


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
        self.assertEqual(dialog.apps_table.item(0, 1).text(), "⚙️ Exec: kitty\n📄 Desktop: kitty.desktop")

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

    @patch('core.monitor_main.AppMonitor')
    @patch('utils.systemd_manager.is_active', return_value=False)
    @patch('psutil.process_iter')
    @patch('subprocess.Popen')
    @patch('PySide6.QtWidgets.QMessageBox.information')
    @patch('utils.systemd_manager.is_enabled', return_value=True)
    def test_restart_daemon_manual(self, mock_enabled, mock_info, mock_popen, mock_iter, mock_active, mock_app_monitor):
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

    @patch('core.monitor_main.AppMonitor')
    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_sleep_relocks_all_apps(self, mock_dbus, mock_app_monitor):
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

    @patch('core.monitor_main.AppMonitor')
    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_screensaver_relocks_all_apps(self, mock_dbus, mock_app_monitor):
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

    @patch('core.monitor_main.AppMonitor')
    @patch('core.monitor_main.register_dbus_service', return_value=True)
    def test_quit_clears_cached_key(self, mock_dbus, mock_app_monitor):
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

    @patch('security.lockout_manager.is_locked_out', return_value=(False, 0))
    @patch('core.monitor_main.AppMonitor')
    @patch('core.monitor_main.register_dbus_service', return_value=True)
    @patch('core.monitor_main.FaceGateApplication._run_recognition_subprocess', return_value=(True, "face", 0.9, "admin"))
    @patch('database.embedding_store.load_embeddings',
           return_value={"test_user": np.zeros(512)})
    def test_enrollment_requires_both_password_and_face(self, mock_load, mock_run_sub, mock_dbus, mock_app_monitor, mock_lockout):
        """Enrollment must require face verification when users exist."""
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
            mock_run_sub.assert_called_once_with("Enrollment Access")
            mock_show.assert_called_once()

    @patch('core.monitor_main.AppMonitor')
    @patch('core.monitor_main.register_dbus_service', return_value=True)
    @patch('core.monitor_main.FaceGateApplication._run_recognition_subprocess', return_value=(True, "password", None, "admin"))
    @patch('database.embedding_store.load_embeddings', return_value={})
    @patch('core.monitor_main.os.path.exists', return_value=False)
    def test_enrollment_skips_face_when_no_users(self, mock_exists, mock_load, mock_run_sub, mock_dbus, mock_app_monitor):
        """Enrollment with no enrolled users must skip verification on first run."""
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
            mock_run_sub.assert_not_called()
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

    @patch('database.embedding_store.get_cached_key', return_value=b'12345678901234567890123456789012')
    @patch('ui.enrollment_wizard.get_cached_key', return_value=b'12345678901234567890123456789012')
    @patch('ui.enrollment_wizard.load_embeddings', return_value={'ScaraMouche': np.zeros((512,))})
    @patch('PySide6.QtWidgets.QMessageBox.warning')
    def test_blocks_duplicate_username_enrollment(self, mock_warning, mock_load, mock_key_ui, mock_key_db):
        """EnrollmentWizard must strictly block duplicate username enrollment when target_username is None."""
        from ui.enrollment_wizard import EnrollmentWizard
        wizard = EnrollmentWizard()
        wizard.username_input.setText("scaramouche")  # Case-insensitive match for ScaraMouche
        wizard.process_intro_next()
        mock_warning.assert_called_once()
        self.assertIn("already enrolled", mock_warning.call_args[0][2].lower())

    @patch('database.embedding_store.load_embeddings', return_value={'existing_user': np.ones((512,), dtype=np.float32)})
    @patch('ui.enrollment_wizard.load_embeddings', return_value={'existing_user': np.ones((512,), dtype=np.float32)})
    def test_detects_duplicate_face_vector(self, mock_load_ui, mock_load_db):
        """EnrollmentWizard must detect duplicate face vectors and present a warning."""
        from ui.enrollment_wizard import EnrollmentWizard
        wizard = EnrollmentWizard(target_username="new_user")
        wizard.username = "new_user"

        # Simulate captured faces with high similarity to existing_user
        faces = [{'bbox': [10, 10, 50, 50], 'embedding': np.ones((512,), dtype=np.float32)}]
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

        with patch('ui.enrollment_wizard.is_blurry', return_value=False):
            with patch.object(wizard, 'cleanup_camera'):
                for _ in range(15):
                    wizard.on_detection_result(faces, dummy_frame)

        self.assertEqual(wizard.duplicate_user, "existing_user")
        self.assertGreater(wizard.duplicate_similarity, 0.99)
        self.assertIn("Duplicate Face Profile Detected", wizard.success_msg_lbl.text())


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
        
        c_dark = get_colors("dark")
        c_light = get_colors("light")
        
        qss_dark = get_sidebar_qss(c_dark)
        qss_light = get_sidebar_qss(c_light)
        
        self.assertIn(c_dark["SIDEBAR_BG"], qss_dark)
        self.assertIn(c_light["SIDEBAR_BG"], qss_light)


class TestColorPaletteSystem(unittest.TestCase):
    """Tests for the Color Palette preset system and dynamic resolution."""

    def test_all_palettes_have_valid_structure(self):
        """Every palette in PALETTES registry must define light and dark theme maps with all required keys."""
        from ui.theme import PALETTES
        required_keys = [
            "IS_DARK", "BG_NEUTRAL", "BG_SECONDARY", "CARD_NEUTRAL", "BORDER_NEUTRAL",
            "TEXT_PRIMARY", "TEXT_SECONDARY", "ACCENT_PURPLE", "ACCENT_PURPLE_HOVER",
            "ACCENT_PURPLE_PRESSED", "WIDGET_BG", "LIST_ITEM_HOVER", "HOVER_NEUTRAL",
            "CANCEL_BTN_BG", "CANCEL_BTN_HOVER", "SIDEBAR_BG", "SIDEBAR_COLOR"
        ]
        for key, p_info in PALETTES.items():
            self.assertIn("label", p_info)
            self.assertIn("dark", p_info)
            self.assertIn("light", p_info)
            for mode in ["dark", "light"]:
                for r_key in required_keys:
                    self.assertIn(r_key, p_info[mode], f"Palette '{key}' mode '{mode}' missing key '{r_key}'")

    def test_get_colors_resolves_palette_preset(self):
        """get_colors must return exact palette colors when palette_override is supplied."""
        from ui.theme import get_colors
        c_iron_dark = get_colors(theme_override="dark", palette_override="iron_ember")
        self.assertEqual(c_iron_dark["ACCENT_PURPLE"], "#f97316")

        c_violet_light = get_colors(theme_override="light", palette_override="violet_slate")
        self.assertEqual(c_violet_light["ACCENT_PURPLE"], "#7c3aed")

        c_emerald_dark = get_colors(theme_override="dark", palette_override="emerald_obsidian")
        self.assertEqual(c_emerald_dark["ACCENT_PURPLE"], "#10b981")

        c_amber_light = get_colors(theme_override="light", palette_override="amber_espresso")
        self.assertEqual(c_amber_light["ACCENT_PURPLE"], "#d97706")

    def test_get_colors_falls_back_on_invalid_palette(self):
        """get_colors must fall back to iron_ember when an invalid palette key is passed."""
        from ui.theme import get_colors
        c = get_colors(theme_override="light", palette_override="non_existent_palette")
        self.assertEqual(c["ACCENT_PURPLE"], "#c2410c")


class TestTrayIconPresets(unittest.TestCase):
    """Tests for system tray icon preset glyph renderers."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_all_tray_icon_renderers_produce_valid_qicon(self):
        """All 5 tray icon styles must render non-null QIcon instances."""
        from ui.tray import TRAY_ICON_STYLES, get_tray_icon_renderer
        test_color = "#c2410c"
        for style_name, renderer in TRAY_ICON_STYLES.items():
            icon = renderer(test_color)
            self.assertFalse(icon.isNull(), f"Tray icon style '{style_name}' returned a null QIcon")

        fallback_icon = get_tray_icon_renderer("invalid_style")(test_color)
        self.assertFalse(fallback_icon.isNull(), "Fallback tray icon renderer returned null QIcon")


class TestAnimatedComboBoxPopup(unittest.TestCase):
    """Tests for AnimatedComboBox single rounded-rectangle popup styling."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_animated_combobox_translucent_container(self):
        """AnimatedComboBox must set translucent background on container while keeping QListView solid opaque."""
        from PySide6.QtCore import Qt
        from ui.theme import AnimatedComboBox
        combo = AnimatedComboBox()
        combo.addItem("Option 1", "opt1")
        combo.addItem("Option 2", "opt2")
        combo._apply_view_style()

        view = combo.view()
        self.assertIsNotNone(view)
        self.assertFalse(view.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        container = view.parentWidget()
        if container:
            self.assertTrue(container.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))


if __name__ == "__main__":
    unittest.main()
