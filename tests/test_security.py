"""
Tests for the embedding_store and credential_store security layer.
Validates that the hardcoded password has been removed, the cached key
uses bytearray for secure zeroing, and the envelope read/write cycle
works correctly with proper file permissions.
"""
import os
import sys
import json
import base64
import tempfile
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

# Patch the EMBEDDING_FILE and OLD_EMBEDDING_FILE paths to use temp directory
# before importing the module under test.


@pytest.fixture(autouse=True)
def temp_embedding_paths(tmp_path):
    """Redirect all file operations to a temp directory for isolation."""
    enc_path = str(tmp_path / "embeddings.enc")
    old_path = str(tmp_path / "embeddings.json")
    with patch("database.embedding_store.EMBEDDING_FILE", enc_path), \
         patch("database.embedding_store.OLD_EMBEDDING_FILE", old_path):
        from database.embedding_store import clear_cached_key
        clear_cached_key()
        yield {"enc": enc_path, "old": old_path, "dir": tmp_path}
        clear_cached_key()


class TestHardcodedPasswordRemoved:
    """Verify that the critical C1 fix is in place — no hardcoded passwords."""

    def test_no_hardcoded_password_in_source(self):
        """The string 'password123' must not appear anywhere in embedding_store.py."""
        import inspect
        import database.embedding_store as es
        source = inspect.getsource(es)
        assert "password123" not in source, \
            "CRITICAL: Hardcoded password 'password123' found in embedding_store.py"

    def test_get_or_prompt_key_returns_none_without_cached_key(self):
        """Without a cached key, get_or_prompt_key() must return None (not auto-init)."""
        from database.embedding_store import get_or_prompt_key
        result = get_or_prompt_key()
        assert result is None, \
            "get_or_prompt_key() must return None when no key is cached (no auto-init)"

    def test_get_or_prompt_key_returns_cached_key(self):
        """If a key is cached, get_or_prompt_key() must return it."""
        from database.embedding_store import get_or_prompt_key, set_cached_key
        test_key = os.urandom(32)
        set_cached_key(test_key)
        result = get_or_prompt_key()
        assert result == test_key


class TestCachedKeyMemorySafety:
    """Verify that the cached key uses bytearray and can be securely zeroed (H3 fix)."""

    def test_cached_key_stored_as_bytearray(self):
        """The internal cached key must be a bytearray (not immutable bytes)."""
        from database.embedding_store import set_cached_key
        import database.embedding_store as es
        set_cached_key(os.urandom(32))
        assert isinstance(es._cached_key, bytearray), \
            "Cached key must be bytearray for secure zeroing"

    def test_clear_cached_key_zeros_memory(self):
        """After clear_cached_key(), the key buffer must be all zeroes and then None."""
        from database.embedding_store import set_cached_key, clear_cached_key
        import database.embedding_store as es

        key = os.urandom(32)
        set_cached_key(key)
        buf = es._cached_key  # Hold a reference to the buffer
        clear_cached_key()

        # The buffer should be zeroed
        assert all(b == 0 for b in buf), "Key buffer must be zeroed after clear"
        # The global should be None
        assert es._cached_key is None

    def test_get_cached_key_returns_bytes_copy(self):
        """get_cached_key() must return a bytes copy (not the internal bytearray)."""
        from database.embedding_store import set_cached_key, get_cached_key
        set_cached_key(os.urandom(32))
        result = get_cached_key()
        assert isinstance(result, bytes), \
            "get_cached_key() should return bytes (a copy), not the internal bytearray"


class TestEnvelopeRoundTrip:
    """Tests for reading/writing the encrypted envelope file."""

    def test_save_and_load_embedding(self, temp_embedding_paths):
        """save_embedding + load_embeddings must round-trip correctly."""
        from security.crypto_engine import derive_key
        from database.embedding_store import set_cached_key, save_embedding, load_embeddings

        # Derive and cache a key
        password = b"test-master-password"
        salt = os.urandom(16)
        key = derive_key(password, salt, iterations=1000)
        set_cached_key(key)

        # Create a test embedding
        test_embedding = np.random.randn(512).astype(np.float32)
        save_embedding("test_user", test_embedding)

        # Verify file exists with correct permissions
        enc_path = temp_embedding_paths["enc"]
        assert os.path.exists(enc_path)
        mode = oct(os.stat(enc_path).st_mode & 0o777)
        assert mode == "0o600", f"Embedding file should have 0o600 permissions, got {mode}"

        # Load back and verify
        loaded = load_embeddings()
        assert "test_user" in loaded
        np.testing.assert_array_almost_equal(loaded["test_user"], test_embedding, decimal=5)

    def test_read_envelope_returns_none_for_missing_file(self, temp_embedding_paths):
        """read_envelope_file() must return None if the file doesn't exist."""
        from database.embedding_store import read_envelope_file
        result = read_envelope_file()
        assert result is None

    def test_read_envelope_returns_none_for_malformed_json(self, temp_embedding_paths):
        """read_envelope_file() must return None for corrupt JSON."""
        enc_path = temp_embedding_paths["enc"]
        os.makedirs(os.path.dirname(enc_path), exist_ok=True)
        with open(enc_path, 'w') as f:
            f.write("not valid json {{{")

        from database.embedding_store import read_envelope_file
        result = read_envelope_file()
        assert result is None

    def test_save_embedding_raises_runtime_error_without_key(self, temp_embedding_paths):
        """save_embedding() must raise RuntimeError if no encryption key is cached or available."""
        from database.embedding_store import save_embedding, clear_cached_key
        clear_cached_key()
        test_embedding = np.random.randn(512).astype(np.float32)
        with pytest.raises(RuntimeError, match="no encryption key available"):
            save_embedding("test_user", test_embedding)


class TestCredentialStorePasswordVerification:
    """Tests for verify_password() in the credential store."""

    def test_verify_correct_password(self, temp_embedding_paths):
        """verify_password() must return True for the correct password."""
        from security.crypto_engine import derive_key, encrypt
        from security.credential_store import verify_password

        password = "MySecurePass!123"
        salt = os.urandom(16)
        iterations = 1000
        key = derive_key(password.encode('utf-8'), salt, iterations)

        plaintext = json.dumps({}).encode('utf-8')
        nonce, ciphertext = encrypt(plaintext, key)

        envelope = {
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()
        }

        enc_path = temp_embedding_paths["enc"]
        os.makedirs(os.path.dirname(enc_path), exist_ok=True)
        with open(enc_path, 'w') as f:
            json.dump(envelope, f)

        assert verify_password(password) is True

    def test_verify_wrong_password(self, temp_embedding_paths):
        """verify_password() must return False for incorrect password."""
        from security.crypto_engine import derive_key, encrypt
        from security.credential_store import verify_password

        correct_pwd = "CorrectPassword"
        salt = os.urandom(16)
        iterations = 1000
        key = derive_key(correct_pwd.encode('utf-8'), salt, iterations)

        plaintext = json.dumps({}).encode('utf-8')
        nonce, ciphertext = encrypt(plaintext, key)

        envelope = {
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()
        }

        enc_path = temp_embedding_paths["enc"]
        os.makedirs(os.path.dirname(enc_path), exist_ok=True)
        with open(enc_path, 'w') as f:
            json.dump(envelope, f)

        assert verify_password("WrongPassword") is False

    def test_verify_empty_password(self, temp_embedding_paths):
        """verify_password() must return False for empty string."""
        from security.credential_store import verify_password
        assert verify_password("") is False

    def test_password_bytearray_zeroed_after_verify(self, temp_embedding_paths):
        """The password bytearray should be zeroed after verification (memory hygiene)."""
        # This test verifies the structure — the actual zeroing happens inside
        # verify_password's finally block. We verify by checking the function
        # source code for the zeroing pattern.
        import inspect
        from security.credential_store import verify_password
        source = inspect.getsource(verify_password)
        assert "pwd_bytes[i] = 0" in source, \
            "Password zeroing pattern not found in verify_password"


class TestAdminFaceVerification:
    """Tests for FaceGateApplication.verify_admin_face validation behavior (Item 1)."""

    @patch('PySide6.QtWidgets.QSystemTrayIcon.isSystemTrayAvailable', return_value=False)
    @patch('core.monitor_main.AppMonitor')
    @patch('core.monitor_main.register_dbus_service', return_value=True)
    @patch('core.monitor_main.FaceGateApplication._run_recognition_subprocess', return_value=(True, "face", 0.9, "admin"))
    @patch('database.embedding_store.load_embeddings')
    @patch('os.path.exists')
    def test_verify_admin_face_states(self, mock_exists, mock_load, mock_run_sub, mock_dbus, mock_app_monitor, mock_tray):
        from core.monitor_main import FaceGateApplication
        from utils.config_loader import Config

        mock_config = Config()
        mock_config.settings = {
            "app_monitor": {"auth_timeout_seconds": 60},
        }
        app = FaceGateApplication(config=mock_config)

        # State 1: Fresh boot / true first-run (no enrolled faces, no database exists)
        mock_load.return_value = {}
        mock_exists.return_value = False

        res = app.verify_admin_face("test_reason")
        assert res is True, "First-run should bypass and return True immediately"
        mock_run_sub.assert_not_called()

        # State 2: Locked daemon with existing database (no cached key, so load_embeddings returns {}, but file exists)
        mock_load.return_value = {}
        mock_exists.return_value = True
        mock_run_sub.reset_mock()

        res = app.verify_admin_face("test_reason")
        assert res is True, "Should require recognition subprocess and return True when Accepted"
        mock_run_sub.assert_called_once_with("test_reason")

        # State 3: Unlocked daemon (key is cached, load_embeddings returns face templates, file exists)
        mock_load.return_value = {"admin": np.zeros(512)}
        mock_exists.return_value = True
        mock_run_sub.reset_mock()

        res = app.verify_admin_face("test_reason")
        assert res is True, "Should require recognition subprocess and return True when Accepted"
        mock_run_sub.assert_called_once_with("test_reason")


class TestDBusSecurityHardening:
    """Tests for D-Bus interface security hardening (Audit §1.1, §1.2, §1.3)."""

    def test_dbus_adaptor_does_not_expose_get_or_update_cached_key(self):
        """GetCachedKey and UpdateCachedKey must NOT be exposed on FaceGateAdaptor."""
        from locking.ipc_service import FaceGateAdaptor
        assert not hasattr(FaceGateAdaptor, "GetCachedKey"), \
            "CRITICAL: GetCachedKey must NOT be exposed on FaceGateAdaptor"
        assert not hasattr(FaceGateAdaptor, "UpdateCachedKey"), \
            "CRITICAL: UpdateCachedKey must NOT be exposed on FaceGateAdaptor"

    def test_remove_enrolled_user_requires_admin_face_verification(self):
        """RemoveEnrolledUser D-Bus call must require admin face verification."""
        from locking.ipc_service import FaceGateService
        mock_app = MagicMock()
        mock_app.verify_admin_face.return_value = False
        service = FaceGateService(main_app=mock_app)

        result = service.remove_enrolled_user_internal("target_user")
        assert result is False, "RemoveEnrolledUser must fail when admin face verification fails"
        mock_app.verify_admin_face.assert_called_once()

    def test_set_admin_user_requires_admin_face_verification(self):
        """SetAdminUser D-Bus call must require admin face verification."""
        from locking.ipc_service import FaceGateService
        mock_app = MagicMock()
        mock_app.verify_admin_face.return_value = False
        service = FaceGateService(main_app=mock_app)

        result = service.set_admin_user_internal("attacker")
        assert result is False, "SetAdminUser must fail when admin face verification fails"
        mock_app.verify_admin_face.assert_called_once()


class TestCLIEnrollmentAuthentication:
    """Tests for facegate --enroll CLI authentication gate."""

    @patch("sys.exit", side_effect=SystemExit(1))
    @patch("recognition.cli_enroll.enroll_user")
    @patch("security.credential_store.verify_password", return_value=False)
    @patch("sys.stdin.isatty", return_value=True)
    @patch("getpass.getpass", return_value="wrong_password")
    @patch("PySide6.QtDBus.QDBusConnection.sessionBus")
    @patch("PySide6.QtDBus.QDBusInterface")
    @patch("os.path.exists", return_value=True)
    def test_cli_enroll_fails_on_incorrect_password(
        self, mock_exists, mock_interface, mock_bus, mock_getpass, mock_isatty, mock_verify, mock_enroll, mock_exit
    ):
        """facegate --enroll must fail and exit if master password verification fails."""
        mock_bus.return_value.isConnected.return_value = True
        mock_iface_instance = MagicMock()
        mock_iface_instance.isValid.return_value = False
        mock_interface.return_value = mock_iface_instance
        from core.monitor_main import main

        test_args = ["facegate", "--enroll", "attacker"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        mock_enroll.assert_not_called()

    @patch("sys.exit", side_effect=SystemExit(1))
    @patch("recognition.cli_enroll.enroll_user")
    @patch("PySide6.QtDBus.QDBusConnection.sessionBus")
    @patch("PySide6.QtDBus.QDBusInterface")
    @patch("PySide6.QtDBus.QDBusReply")
    @patch("os.path.exists", return_value=True)
    def test_cli_enroll_fails_when_dbus_auth_rejected(
        self, mock_exists, mock_qdbus_reply, mock_interface, mock_bus, mock_enroll, mock_exit
    ):
        """facegate --enroll must fail if D-Bus daemon rejects authentication."""
        mock_bus.return_value.isConnected.return_value = True
        mock_iface_instance = MagicMock()
        mock_iface_instance.isValid.return_value = True
        mock_interface.return_value = mock_iface_instance

        mock_reply_instance = MagicMock()
        mock_reply_instance.isValid.return_value = True
        mock_reply_instance.value.return_value = False  # Auth rejected by daemon
        mock_qdbus_reply.return_value = mock_reply_instance

        from core.monitor_main import main

        test_args = ["facegate", "--enroll", "attacker"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        mock_enroll.assert_not_called()

    @patch("sys.exit", side_effect=SystemExit(0))
    @patch("recognition.cli_enroll.enroll_user")
    @patch("PySide6.QtDBus.QDBusConnection.sessionBus")
    @patch("PySide6.QtDBus.QDBusInterface")
    @patch("PySide6.QtDBus.QDBusReply")
    @patch("os.path.exists", return_value=True)
    def test_cli_enroll_succeeds_when_dbus_auth_accepted(
        self, mock_exists, mock_qdbus_reply, mock_interface, mock_bus, mock_enroll, mock_exit
    ):
        """facegate --enroll must proceed to enroll_user if D-Bus daemon accepts authentication."""
        mock_bus.return_value.isConnected.return_value = True
        mock_iface_instance = MagicMock()
        mock_iface_instance.isValid.return_value = True
        mock_interface.return_value = mock_iface_instance

        mock_reply_instance = MagicMock()
        mock_reply_instance.isValid.return_value = True
        mock_reply_instance.value.return_value = True  # Auth accepted by daemon
        mock_qdbus_reply.return_value = mock_reply_instance

        from core.monitor_main import main

        test_args = ["facegate", "--enroll", "valid_user"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_enroll.assert_called_once_with("valid_user")


class TestPersistentLockoutManager:
    """Tests for persistent cross-process brute-force lockout manager."""

    @pytest.fixture(autouse=True)
    def temp_lockout_file(self, tmp_path):
        lockout_path = str(tmp_path / "lockout.json")
        with patch("security.lockout_manager.LOCKOUT_FILE", lockout_path):
            from security.lockout_manager import reset_lockout
            reset_lockout()
            yield lockout_path
            reset_lockout()

    def test_lockout_escalation_and_persistence(self, temp_lockout_file):
        from security.lockout_manager import is_locked_out, record_failed_attempt, reset_lockout

        app_name = "test_app"
        locked, _ = is_locked_out(app_name)
        assert not locked

        # 1st attempt
        record_failed_attempt(app_name)
        locked, _ = is_locked_out(app_name)
        assert not locked

        # 2nd attempt
        record_failed_attempt(app_name)
        locked, _ = is_locked_out(app_name)
        assert not locked

        # 3rd attempt -> 2s lockout
        attempts, lockout_until, remaining = record_failed_attempt(app_name)
        assert attempts == 3
        assert remaining > 0
        locked, rem = is_locked_out(app_name)
        assert locked
        assert rem > 0
        assert os.path.exists(temp_lockout_file)

        # Reset
        reset_lockout(app_name)
        locked, _ = is_locked_out(app_name)
        assert not locked

    def test_ipc_service_blocks_locked_out_requests(self, temp_lockout_file):
        from security.lockout_manager import record_failed_attempt
        from locking.ipc_service import FaceGateService

        app_name = "target_app"
        # Trigger lockout (3 failed attempts)
        for _ in range(3):
            record_failed_attempt(app_name)

        service = FaceGateService()
        result = service.request_auth_internal(app_name)
        assert result is False, "IPC service RequestAuth must return False when app is locked out"




