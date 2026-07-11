"""
Tests for the FaceGate cryptographic engine.
Covers AES-256-GCM encryption, PBKDF2 key derivation, tamper detection,
nonce uniqueness, and edge cases.
"""
import os
import pytest
from security.crypto_engine import derive_key, encrypt, decrypt
from cryptography.exceptions import InvalidTag


class TestKeyDerivation:
    """Tests for PBKDF2-HMAC-SHA256 key derivation."""

    def test_derives_256_bit_key(self):
        """Key derivation must produce exactly 32 bytes (256 bits)."""
        key = derive_key(b"password", os.urandom(16), iterations=1000)
        assert len(key) == 32

    def test_deterministic_with_same_inputs(self):
        """Same password + salt + iterations must produce identical keys."""
        salt = os.urandom(16)
        key1 = derive_key(b"same-password", salt, iterations=1000)
        key2 = derive_key(b"same-password", salt, iterations=1000)
        assert key1 == key2

    def test_different_salt_produces_different_key(self):
        """Different salts must produce different keys even for the same password."""
        password = b"same-password"
        key1 = derive_key(password, os.urandom(16), iterations=1000)
        key2 = derive_key(password, os.urandom(16), iterations=1000)
        assert key1 != key2

    def test_different_password_produces_different_key(self):
        """Different passwords must produce different keys for the same salt."""
        salt = os.urandom(16)
        key1 = derive_key(b"password-one", salt, iterations=1000)
        key2 = derive_key(b"password-two", salt, iterations=1000)
        assert key1 != key2


class TestEncryptionRoundTrip:
    """Tests for AES-256-GCM encrypt/decrypt cycle."""

    def test_round_trip(self):
        """Encrypt then decrypt must return original plaintext."""
        key = derive_key(b"SuperSecretPassword123", os.urandom(16), iterations=1000)
        plaintext = b"facegate-encrypted-payload"

        nonce, ciphertext = encrypt(plaintext, key)
        assert len(nonce) == 12
        assert ciphertext != plaintext

        decrypted = decrypt(nonce, ciphertext, key)
        assert decrypted == plaintext

    def test_empty_plaintext(self):
        """Encrypting empty bytes must round-trip correctly."""
        key = derive_key(b"key", os.urandom(16), iterations=1000)
        nonce, ciphertext = encrypt(b"", key)
        decrypted = decrypt(nonce, ciphertext, key)
        assert decrypted == b""

    def test_large_payload(self):
        """Encrypting a payload larger than typical embeddings (1 MB) must work."""
        key = derive_key(b"key", os.urandom(16), iterations=1000)
        plaintext = os.urandom(1024 * 1024)  # 1 MB
        nonce, ciphertext = encrypt(plaintext, key)
        decrypted = decrypt(nonce, ciphertext, key)
        assert decrypted == plaintext

    def test_unique_nonces_per_encryption(self):
        """Each call to encrypt() must produce a unique nonce (birthday resistance)."""
        key = derive_key(b"key", os.urandom(16), iterations=1000)
        nonces = set()
        for _ in range(100):
            nonce, _ = encrypt(b"data", key)
            nonces.add(nonce)
        assert len(nonces) == 100, "Nonce collision detected — catastrophic for AES-GCM"


class TestTamperDetection:
    """Tests that AES-GCM's authentication tag catches modifications."""

    @pytest.fixture
    def encrypted_payload(self):
        key = derive_key(b"secure-pwd", os.urandom(16), iterations=1000)
        plaintext = b"original-payload-data"
        nonce, ciphertext = encrypt(plaintext, key)
        return key, nonce, ciphertext

    def test_wrong_key_rejected(self):
        """Decrypting with a wrong key must raise InvalidTag."""
        salt = os.urandom(16)
        correct_key = derive_key(b"correct", salt, iterations=1000)
        wrong_key = derive_key(b"wrong", salt, iterations=1000)

        nonce, ciphertext = encrypt(b"secret-embeddings", correct_key)
        with pytest.raises(InvalidTag):
            decrypt(nonce, ciphertext, wrong_key)

    def test_ciphertext_tampering(self, encrypted_payload):
        """Flipping a single bit in the ciphertext must raise InvalidTag."""
        key, nonce, ciphertext = encrypted_payload
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0x01
        with pytest.raises(InvalidTag):
            decrypt(nonce, bytes(tampered), key)

    def test_nonce_tampering(self, encrypted_payload):
        """Flipping a single bit in the nonce must raise InvalidTag."""
        key, nonce, ciphertext = encrypted_payload
        tampered = bytearray(nonce)
        tampered[0] ^= 0x01
        with pytest.raises(InvalidTag):
            decrypt(bytes(tampered), ciphertext, key)

    def test_truncated_ciphertext(self, encrypted_payload):
        """Truncating the ciphertext must raise InvalidTag (tag removed)."""
        key, nonce, ciphertext = encrypted_payload
        with pytest.raises(InvalidTag):
            decrypt(nonce, ciphertext[:-1], key)
