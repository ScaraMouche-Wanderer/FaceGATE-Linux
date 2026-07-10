import os
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def derive_key(password: bytes, salt: bytes, iterations: int) -> bytes:
    """
    Derives a 256-bit (32-byte) key from the given password and salt using PBKDF2-HMAC-SHA256.
    """
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=iterations
    )
    return kdf.derive(password)

def encrypt(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    """
    Encrypts the plaintext using AES-256-GCM with a fresh 96-bit random nonce.
    Returns (nonce, ciphertext_with_tag).
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce, ciphertext

def decrypt(nonce: bytes, ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypts the ciphertext using AES-256-GCM.
    Raises cryptography.exceptions.InvalidTag if decryption fails (e.g. wrong key/tampered data).
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
