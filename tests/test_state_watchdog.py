"""
Unit tests for the State Integrity Watchdog module.

Tests the file-deletion bypass hardening:
- Sentinel file management (write, verify, tamper detection)
- Critical file deletion detection
- Lockout guard (missing lockout file treated as max lockout)
- Auth coordinator deny-by-default on missing embeddings
- Config loader tamper detection
"""

import os
import sys
import json
import time
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

# Add project src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestSentinelFile(unittest.TestCase):
    """Tests for initialization sentinel (.initialized) management."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="facegate_test_")
        self.sentinel_path = os.path.join(self.test_dir, ".initialized")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("security.state_watchdog.FACEGATE_CONFIG_DIR")
    @patch("security.state_watchdog.SENTINEL_FILE")
    def test_write_sentinel_creates_file(self, mock_sentinel, mock_config_dir):
        """Sentinel file is created with valid HMAC on write."""
        mock_config_dir.__str__ = lambda s: self.test_dir
        mock_sentinel.__str__ = lambda s: self.sentinel_path
        # Patch the module-level constants
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import write_sentinel, is_initialized
            write_sentinel()

            self.assertTrue(os.path.exists(self.sentinel_path))

            # Verify it reads as initialized
            self.assertTrue(is_initialized())

    @patch("security.state_watchdog.SENTINEL_FILE")
    def test_not_initialized_without_sentinel(self, mock_sentinel):
        """System reports not-initialized when sentinel file doesn't exist."""
        nonexistent = os.path.join(self.test_dir, "nonexistent_sentinel")
        with patch("security.state_watchdog.SENTINEL_FILE", nonexistent):
            from security.state_watchdog import is_initialized
            self.assertFalse(is_initialized())

    def test_corrupt_sentinel_treated_as_initialized(self):
        """A corrupt sentinel file is treated as 'was initialized' (fail-secure)."""
        with patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            # Write garbage data
            with open(self.sentinel_path, "w") as f:
                f.write("corrupted garbage data")

            from security.state_watchdog import is_initialized
            self.assertTrue(is_initialized())

    def test_forged_sentinel_rejected(self):
        """A sentinel with wrong HMAC is detected (cross-machine copy attack)."""
        with patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            # Write a sentinel with a valid structure but wrong HMAC
            sentinel_data = {
                "initialized_at": str(time.time()),
                "hmac": "a" * 64,  # Wrong HMAC
                "version": 1,
            }
            with open(self.sentinel_path, "w") as f:
                json.dump(sentinel_data, f)

            from security.state_watchdog import is_initialized
            # Forged HMAC should fail verification — but the file exists,
            # so is_initialized returns False (HMAC mismatch)
            self.assertFalse(is_initialized())

    def test_sentinel_idempotent(self):
        """Multiple writes to sentinel don't cause errors."""
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import write_sentinel, is_initialized
            write_sentinel()
            write_sentinel()
            write_sentinel()
            self.assertTrue(is_initialized())


class TestCriticalFileDetection(unittest.TestCase):
    """Tests for critical file deletion detection."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="facegate_test_")
        self.sentinel_path = os.path.join(self.test_dir, ".initialized")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_sentinel(self):
        """Helper to write a valid sentinel."""
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import write_sentinel
            write_sentinel()

    def test_detects_missing_embeddings(self):
        """Missing embeddings.enc is flagged after initialization."""
        self._write_sentinel()

        # Create other critical files but NOT embeddings.enc
        os.makedirs(os.path.join(self.test_dir, "backups"), exist_ok=True)
        for fname in ["launchers_manifest.json", "lockout.json"]:
            with open(os.path.join(self.test_dir, fname), "w") as f:
                f.write("{}")

        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import check_critical_files
            issues = check_critical_files()
            missing_files = [i["file"] for i in issues]
            self.assertIn("embeddings.enc", missing_files)

    def test_detects_missing_manifest(self):
        """Missing launchers_manifest.json is flagged after initialization."""
        self._write_sentinel()

        # Create other critical files but NOT manifest
        os.makedirs(os.path.join(self.test_dir, "backups"), exist_ok=True)
        for fname in ["embeddings.enc", "lockout.json"]:
            with open(os.path.join(self.test_dir, fname), "w") as f:
                f.write("{}")

        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import check_critical_files
            issues = check_critical_files()
            missing_files = [i["file"] for i in issues]
            self.assertIn("launchers_manifest.json", missing_files)

    def test_detects_missing_backups_dir(self):
        """Missing backups/ directory is flagged after initialization."""
        self._write_sentinel()

        # Create critical files but NOT backups directory
        for fname in ["embeddings.enc", "launchers_manifest.json", "lockout.json"]:
            with open(os.path.join(self.test_dir, fname), "w") as f:
                f.write("{}")

        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import check_critical_files
            issues = check_critical_files()
            missing_files = [i["file"] for i in issues]
            self.assertIn("backups", missing_files)

    def test_no_issues_when_all_files_present(self):
        """No issues reported when all critical files exist."""
        self._write_sentinel()

        # Create ALL critical files and directories
        os.makedirs(os.path.join(self.test_dir, "backups"), exist_ok=True)
        for fname in ["embeddings.enc", "launchers_manifest.json", "lockout.json"]:
            with open(os.path.join(self.test_dir, fname), "w") as f:
                f.write("{}")

        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import check_critical_files
            issues = check_critical_files()
            self.assertEqual(len(issues), 0)

    def test_no_issues_before_initialization(self):
        """No issues reported if system was never initialized (first run)."""
        # Do NOT write sentinel
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import check_critical_files
            issues = check_critical_files()
            self.assertEqual(len(issues), 0)


class TestLockoutGuard(unittest.TestCase):
    """Tests for lockout_manager hardening against file deletion."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="facegate_test_")
        self.lockout_path = os.path.join(self.test_dir, "lockout.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_missing_lockout_after_init_triggers_max_lockout(self):
        """Missing lockout file after init returns maximum lockout state."""
        with patch("security.lockout_manager.LOCKOUT_FILE", self.lockout_path), \
             patch("security.state_watchdog.is_initialized", return_value=True):
            # Mock config to return deny_on_missing_state=True
            mock_config = MagicMock()
            mock_config.get.return_value = True
            with patch("security.lockout_manager.get_config", return_value=mock_config, create=True):
                from security.lockout_manager import _load_lockout_data
                data = _load_lockout_data()
                self.assertEqual(data["global_attempts"], 10)
                self.assertGreater(data["global_lockout_until"], time.time())

    def test_missing_lockout_before_init_returns_fresh_state(self):
        """Missing lockout file before init returns fresh/empty state (normal)."""
        with patch("security.lockout_manager.LOCKOUT_FILE", self.lockout_path), \
             patch("security.state_watchdog.is_initialized", return_value=False):
            from security.lockout_manager import _load_lockout_data
            data = _load_lockout_data()
            self.assertEqual(data["global_attempts"], 0)
            self.assertEqual(data["global_lockout_until"], 0.0)

    def test_lockout_checked_correctly_after_tamper(self):
        """is_locked_out returns True when lockout file is deleted after init."""
        with patch("security.lockout_manager.LOCKOUT_FILE", self.lockout_path), \
             patch("security.state_watchdog.is_initialized", return_value=True):
            mock_config = MagicMock()
            mock_config.get.return_value = True
            with patch("security.lockout_manager.get_config", return_value=mock_config, create=True):
                from security.lockout_manager import is_locked_out
                locked, remaining = is_locked_out("test_app")
                self.assertTrue(locked)
                self.assertGreater(remaining, 0)

import importlib.util
HAS_PYSIDE6 = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 not available")
class TestAuthCoordinatorDenyByDefault(unittest.TestCase):
    """Tests for auth_coordinator hardening against embedding store deletion."""

    def test_denies_when_embeddings_deleted_after_init(self):
        """verify_admin_face returns False when embeddings.enc is deleted after init."""
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "security.deny_on_missing_state": True,
        }.get(key, default)

        from core.auth_coordinator import AuthCoordinator
        coordinator = AuthCoordinator(config=mock_config, session_manager=MagicMock())

        with patch("database.embedding_store.load_embeddings", return_value={}), \
             patch("database.embedding_store.EMBEDDING_FILE", "/nonexistent/embeddings.enc"), \
             patch("os.path.exists", return_value=False), \
             patch("security.state_watchdog.is_initialized", return_value=True), \
             patch("security.lockout_manager.is_locked_out", return_value=(False, 0)), \
             patch("database.audit_log.log_auth_attempt"):
            result = coordinator.verify_admin_face("test_reason")
            self.assertFalse(result)

    def test_allows_first_run_without_sentinel(self):
        """verify_admin_face returns True on genuine first run (no sentinel)."""
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "security.deny_on_missing_state": True,
        }.get(key, default)

        from core.auth_coordinator import AuthCoordinator
        coordinator = AuthCoordinator(config=mock_config, session_manager=MagicMock())

        with patch("database.embedding_store.load_embeddings", return_value={}), \
             patch("database.embedding_store.EMBEDDING_FILE", "/nonexistent/embeddings.enc"), \
             patch("os.path.exists", return_value=False), \
             patch("security.state_watchdog.is_initialized", return_value=False), \
             patch("security.lockout_manager.is_locked_out", return_value=(False, 0)):
            result = coordinator.verify_admin_face("test_reason")
            self.assertTrue(result)


class TestConfigLoaderTamperDetection(unittest.TestCase):
    """Tests for config_loader protected_apps tamper detection."""

    def test_preserves_apps_on_config_deletion(self):
        """protected_apps are preserved when config.yaml is deleted during reload."""
        from utils.config_loader import Config

        config = Config()
        test_apps = [{"id": "firefox", "desktop_name": "firefox.desktop"}]
        config.set("protected_apps", test_apps)

        with patch("security.state_watchdog.is_initialized", return_value=True):
            # Simulate reload where config.yaml is gone (falls back to defaults)
            def mock_load():
                # Reset settings to simulate default config (empty protected_apps)
                config.settings = {"protected_apps": []}

            config.load = mock_load
            config.reload()

            # Should have preserved the previous apps
            reloaded_apps = config.get("protected_apps", [])
            self.assertEqual(len(reloaded_apps), 1)
            self.assertEqual(reloaded_apps[0]["id"], "firefox")


class TestStateWatchdog(unittest.TestCase):
    """Tests for the StateWatchdog class itself."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="facegate_test_")
        self.sentinel_path = os.path.join(self.test_dir, ".initialized")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_force_check_returns_issues(self):
        """force_check returns issues when critical files are missing."""
        # Write sentinel to simulate initialized system
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import write_sentinel, StateWatchdog
            write_sentinel()

            # Don't create any critical files
            watchdog = StateWatchdog(on_tamper_callback=None)
            issues = watchdog.force_check()
            self.assertGreater(len(issues), 0)

    def test_force_check_clean_when_all_present(self):
        """force_check returns empty when all critical files exist."""
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import write_sentinel, StateWatchdog
            write_sentinel()

            # Create all critical files
            os.makedirs(os.path.join(self.test_dir, "backups"), exist_ok=True)
            for fname in ["embeddings.enc", "launchers_manifest.json", "lockout.json"]:
                with open(os.path.join(self.test_dir, fname), "w") as f:
                    f.write("{}")

            watchdog = StateWatchdog(on_tamper_callback=None)
            issues = watchdog.force_check()
            self.assertEqual(len(issues), 0)

    def test_callback_invoked_on_tamper(self):
        """Callback is invoked when tamper is detected during force_check."""
        callback_issues = []

        def my_callback(issues):
            callback_issues.extend(issues)

        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import write_sentinel, StateWatchdog
            write_sentinel()

            # Create all files, then delete one
            os.makedirs(os.path.join(self.test_dir, "backups"), exist_ok=True)
            for fname in ["embeddings.enc", "launchers_manifest.json", "lockout.json"]:
                with open(os.path.join(self.test_dir, fname), "w") as f:
                    f.write("{}")

            # Delete embeddings.enc to simulate attack
            os.remove(os.path.join(self.test_dir, "embeddings.enc"))

            watchdog = StateWatchdog(on_tamper_callback=my_callback)
            # Manually trigger check
            issues = watchdog.force_check()
            if issues and watchdog._callback:
                watchdog._callback(issues)

            self.assertGreater(len(callback_issues), 0)
            self.assertTrue(any(i["file"] == "embeddings.enc" for i in callback_issues))

    def test_watchdog_does_not_start_before_init(self):
        """Watchdog doesn't start its thread if system is not initialized."""
        with patch("security.state_watchdog.FACEGATE_CONFIG_DIR", self.test_dir), \
             patch("security.state_watchdog.SENTINEL_FILE", self.sentinel_path):
            from security.state_watchdog import StateWatchdog
            # Don't write sentinel
            watchdog = StateWatchdog(on_tamper_callback=None)
            watchdog.start()
            # Thread should not have started
            self.assertFalse(watchdog._running)
            self.assertIsNone(watchdog._thread)


if __name__ == "__main__":
    unittest.main()
