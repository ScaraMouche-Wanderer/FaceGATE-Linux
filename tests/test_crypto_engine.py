import os
import pytest
from security.crypto_engine import derive_key, encrypt, decrypt
from cryptography.exceptions import InvalidTag

def test_crypto_round_trip():
    # Test valid key derivation, encryption, and decryption
    password = b"SuperSecretPassword123"
    salt = os.urandom(16)
    iterations = 1000  # Lower count for fast testing
    
    key = derive_key(password, salt, iterations)
    assert len(key) == 32
    
    plaintext = b"facegate-encrypted-payload"
    nonce, ciphertext = encrypt(plaintext, key)
    
    assert len(nonce) == 12
    assert ciphertext != plaintext
    
    decrypted = decrypt(nonce, ciphertext, key)
    assert decrypted == plaintext

def test_wrong_password_rejection():
    # Test that a wrong key raises InvalidTag during decryption
    password = b"correct-password"
    wrong_password = b"incorrect-password"
    salt = os.urandom(16)
    iterations = 1000
    
    key = derive_key(password, salt, iterations)
    wrong_key = derive_key(wrong_password, salt, iterations)
    
    plaintext = b"secret-embeddings"
    nonce, ciphertext = encrypt(plaintext, key)
    
    with pytest.raises(InvalidTag):
        decrypt(nonce, ciphertext, wrong_key)

def test_ciphertext_tampering_detection():
    # Test that tampering with a single byte of ciphertext causes decryption failure
    password = b"secure-pwd"
    salt = os.urandom(16)
    iterations = 1000
    
    key = derive_key(password, salt, iterations)
    plaintext = b"original-payload-data"
    nonce, ciphertext = encrypt(plaintext, key)
    
    # Tamper with the ciphertext (flip a bit in the last byte)
    tampered_ciphertext = bytearray(ciphertext)
    tampered_ciphertext[-1] ^= 0x01
    tampered_ciphertext = bytes(tampered_ciphertext)
    
    with pytest.raises(InvalidTag):
        decrypt(nonce, tampered_ciphertext, key)

def test_nonce_tampering_detection():
    # Test that tampering with the nonce causes decryption failure
    password = b"secure-pwd"
    salt = os.urandom(16)
    iterations = 1000
    
    key = derive_key(password, salt, iterations)
    plaintext = b"original-payload-data"
    nonce, ciphertext = encrypt(plaintext, key)
    
    # Tamper with the nonce (flip a bit in the first byte)
    tampered_nonce = bytearray(nonce)
    tampered_nonce[0] ^= 0x01
    tampered_nonce = bytes(tampered_nonce)
    
    with pytest.raises(InvalidTag):
        decrypt(tampered_nonce, ciphertext, key)
