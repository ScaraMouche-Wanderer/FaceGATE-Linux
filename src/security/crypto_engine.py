import os
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from typing import Optional, Union

def derive_key(password: Union[bytes, bytearray], salt: bytes, iterations: int) -> bytes:
    """
    Derives a 256-bit (32-byte) key from the given password and salt using PBKDF2-HMAC-SHA256.
    """
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=iterations
    )
    return kdf.derive(bytes(password))

def build_aad(kdf_name: str, iterations: int, salt: Union[bytes, str]) -> bytes:
    """
    Constructs canonical Associated Authenticated Data (AAD) to bind
    KDF parameters to AES-256-GCM ciphertexts.
    """
    salt_str = salt.hex() if isinstance(salt, bytes) else str(salt)
    return f"kdf={kdf_name};iterations={iterations};salt={salt_str}".encode('utf-8')

def encrypt(plaintext: bytes, key: bytes, aad: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """
    Encrypts the plaintext using AES-256-GCM with a fresh 96-bit random nonce.
    Optionally authenticates additional associated data (AAD) to bind
    non-secret metadata (e.g. KDF params) to the ciphertext.
    Returns (nonce, ciphertext_with_tag).
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext

def decrypt(nonce: bytes, ciphertext: bytes, key: bytes, aad: Optional[bytes] = None) -> bytes:
    """
    Decrypts the ciphertext using AES-256-GCM.
    If AAD was used during encryption, the same AAD must be provided here.
    Raises cryptography.exceptions.InvalidTag if decryption fails (e.g. wrong key/tampered data/tampered AAD).
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)
