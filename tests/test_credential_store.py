import os
import json
import base64
import pytest
from unittest.mock import patch

from security.credential_store import (
    verify_password, update_master_password
)
from database.embedding_store import (
    set_cached_key, clear_cached_key, get_cached_key
)
from security.crypto_engine import derive_key, encrypt

@pytest.fixture(autouse=True)
def clean_keys():
    clear_cached_key()
    yield
    clear_cached_key()

def test_update_and_verify_master_password(tmp_path):
    enc_path = str(tmp_path / "embeddings.enc")
    with patch("database.embedding_store.EMBEDDING_FILE", enc_path), \
         patch("security.credential_store.EMBEDDING_FILE", enc_path):
        
        # 1. First setup master password
        update_master_password(None, "MasterPassword123!")
        assert os.path.exists(enc_path)

        # File permissions check (must be 0600)
        mode = os.stat(enc_path).st_mode & 0o777
        assert mode == 0o600

        # Verify correct password succeeds
        assert verify_password("MasterPassword123!") is True
        assert get_cached_key() is not None

        # Clear key and verify incorrect password fails
        clear_cached_key()
        assert verify_password("WrongPassword123!") is False
        assert get_cached_key() is None

def test_aad_tampering_rejection(tmp_path):
    """
    Tests that tampering with KDF params or ciphertext when 'kdf' is present
    causes decryption/verification to fail without silently trying aad=None.
    """
    enc_path = str(tmp_path / "embeddings.enc")
    with patch("database.embedding_store.EMBEDDING_FILE", enc_path), \
         patch("security.credential_store.EMBEDDING_FILE", enc_path):
        
        update_master_password(None, "SuperSecret123!")
        
        # Read and tamper with the salt in envelope
        with open(enc_path, "r") as f:
            envelope = json.load(f)
            
        assert "kdf" in envelope
        # Modify salt to simulate tampering oracle attack
        tampered_salt = os.urandom(16)
        envelope["salt"] = base64.b64encode(tampered_salt).decode("utf-8")
        
        with open(enc_path, "w") as f:
            json.dump(envelope, f)
            
        clear_cached_key()
        # Should fail verification and NOT fallback to aad=None
        assert verify_password("SuperSecret123!") is False

def test_legacy_envelope_auto_migration(tmp_path):
    """
    Tests that a legacy envelope without 'kdf' key automatically migrates
    to AAD-bound envelope upon successful password verification.
    """
    enc_path = str(tmp_path / "embeddings.enc")
    with patch("database.embedding_store.EMBEDDING_FILE", enc_path), \
         patch("security.credential_store.EMBEDDING_FILE", enc_path):
        
        password = "LegacyPassword123!"
        pwd_bytes = password.encode("utf-8")
        salt = os.urandom(16)
        iterations = 100000
        key = derive_key(pwd_bytes, salt, iterations)
        
        # Encrypt without AAD (legacy format)
        data = json.dumps({"test_user": [0.1, 0.2, 0.3]}).encode("utf-8")
        nonce, ciphertext = encrypt(data, key, aad=None)
        
        legacy_envelope = {
            # "kdf" is omitted intentionally for legacy envelopes
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8")
        }
        
        with open(enc_path, "w") as f:
            json.dump(legacy_envelope, f)
        os.chmod(enc_path, 0o600)
        
        clear_cached_key()
        # Verify legacy password works
        assert verify_password(password) is True
        
        # Check that envelope was updated in-place to include 'kdf'
        with open(enc_path, "r") as f:
            updated_envelope = json.load(f)
            
        assert "kdf" in updated_envelope
        assert updated_envelope["kdf"] == "pbkdf2_hmac_sha256"

def test_ram_key_file_permissions(tmp_path):
    """
    Asserts that cached RAM key file is created with strict 0600 permissions.
    """
    ram_file = str(tmp_path / "facegate.key")
    with patch("database.embedding_store._get_ram_key_file", return_value=ram_file):
        test_key = b"\x01" * 32
        set_cached_key(test_key)
        
        assert os.path.exists(ram_file)
        mode = os.stat(ram_file).st_mode & 0o777
        assert mode == 0o600
        
        with open(ram_file, "rb") as f:
            read_bytes = f.read()
        assert read_bytes == test_key
