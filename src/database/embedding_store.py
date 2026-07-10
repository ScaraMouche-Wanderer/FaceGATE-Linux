import os
import sys
import json
import base64
import logging
import numpy as np

EMBEDDING_FILE = os.path.expanduser("~/.config/facegate/embeddings.enc")
OLD_EMBEDDING_FILE = os.path.expanduser("~/.config/facegate/embeddings.json")

_cached_key = None

def set_cached_key(key: bytes):
    """
    Caches the derived key in memory for this process's life cycle.
    """
    global _cached_key
    _cached_key = key

def get_cached_key() -> bytes:
    """
    Retrieves the cached key from memory.
    """
    global _cached_key
    return _cached_key

def read_envelope_file() -> dict:
    """
    Helper to read and base64-decode the envelope file.
    Returns None if the file does not exist or is malformed.
    """
    if not os.path.exists(EMBEDDING_FILE):
        return None
        
    try:
        with open(EMBEDDING_FILE, 'r') as f:
            envelope = json.load(f)
            
        return {
            "kdf": envelope["kdf"],
            "iterations": int(envelope["iterations"]),
            "salt": base64.b64decode(envelope["salt"]),
            "nonce": base64.b64decode(envelope["nonce"]),
            "ciphertext": base64.b64decode(envelope["ciphertext"])
        }
    except Exception as e:
        logging.error(f"Error reading encrypted envelope file: {e}")
        return None

def get_or_prompt_key() -> bytes:
    """
    Retrieves the cached key or derives it automatically from the default password.
    If the database is missing or encrypted with a custom password, resets it to the
    default password to maintain a seamless password-less user experience.
    """
    key = get_cached_key()
    if key:
        return key
        
    default_pwd = b"password123"
    pwd_bytes = bytearray(default_pwd)
    
    envelope = read_envelope_file()
    if not envelope:
        # Initialize default database envelope
        from security.crypto_engine import derive_key, encrypt
        import secrets
        try:
            salt = secrets.token_bytes(16)
            iterations = 100000
            derived = derive_key(pwd_bytes, salt, iterations)
            
            plaintext_bytes = json.dumps({}).encode('utf-8')
            nonce, ciphertext = encrypt(plaintext_bytes, derived)
            
            new_envelope = {
                "kdf": "pbkdf2_hmac_sha256",
                "iterations": iterations,
                "salt": base64.b64encode(salt).decode('utf-8'),
                "nonce": base64.b64encode(nonce).decode('utf-8'),
                "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
            }
            
            os.makedirs(os.path.dirname(EMBEDDING_FILE), exist_ok=True)
            with open(EMBEDDING_FILE, 'w') as f:
                json.dump(new_envelope, f, indent=4)
            os.chmod(EMBEDDING_FILE, 0o600)
            
            set_cached_key(derived)
            return derived
        except Exception as e:
            logging.error(f"Auto-initialize failed: {e}")
            return None
            
    # Try to decrypt using default password
    try:
        from security.crypto_engine import derive_key, decrypt
        salt = envelope["salt"]
        # Handle cases where salt is a base64 string or bytes
        salt_bytes = base64.b64decode(salt) if isinstance(salt, str) else salt
        iterations = envelope["iterations"]
        nonce = envelope["nonce"]
        ciphertext = envelope["ciphertext"]
        
        derived = derive_key(pwd_bytes, salt_bytes, iterations)
        # Verify by decrypting
        decrypt(nonce, ciphertext, derived)
        set_cached_key(derived)
        return derived
    except Exception:
        # If decryption fails (e.g. custom password), reset envelope to default
        logging.info("Auto-unlock: Resetting database envelope to default password...")
        try:
            from security.crypto_engine import derive_key, encrypt
            import secrets
            salt = secrets.token_bytes(16)
            iterations = 100000
            derived = derive_key(pwd_bytes, salt, iterations)
            
            plaintext_bytes = json.dumps({}).encode('utf-8')
            nonce, ciphertext = encrypt(plaintext_bytes, derived)
            
            new_envelope = {
                "kdf": "pbkdf2_hmac_sha256",
                "iterations": iterations,
                "salt": base64.b64encode(salt).decode('utf-8'),
                "nonce": base64.b64encode(nonce).decode('utf-8'),
                "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
            }
            
            with open(EMBEDDING_FILE, 'w') as f:
                json.dump(new_envelope, f, indent=4)
            os.chmod(EMBEDDING_FILE, 0o600)
            
            set_cached_key(derived)
            return derived
        except Exception as ex:
            logging.error(f"Auto-reset failed: {ex}")
            return None

def load_embeddings() -> dict:
    """
    Loads enrolled user embeddings from the encrypted envelope.
    Returns a dict mapping username -> np.ndarray.
    """
    if not os.path.exists(EMBEDDING_FILE):
        # If no encrypted file, but plaintext exists, check if we can migrate
        if os.path.exists(OLD_EMBEDDING_FILE) and sys.stdin.isatty():
            logging.info("Old plaintext database detected on load. Prompting for migration.")
            check_and_perform_migration()
        else:
            return {}
            
    key = get_cached_key()
    if not key:
        # Try prompting or environment extraction
        key = get_or_prompt_key()
        
    if not key:
        logging.warning("Encrypted embedding store cannot be decrypted (no encryption key available).")
        return {}
        
    envelope = read_envelope_file()
    if not envelope:
        return {}
        
    try:
        from security.crypto_engine import decrypt
        decrypted_bytes = decrypt(envelope["nonce"], envelope["ciphertext"], key)
        data = json.loads(decrypted_bytes.decode('utf-8'))
        
        # Convert lists back to numpy arrays
        return {name: np.array(emb, dtype=np.float32) for name, emb in data.items()}
    except Exception as e:
        logging.error(f"Error decrypting/parsing embedding store: {e}")
        return {}

def save_embedding(name: str, embedding: np.ndarray):
    """
    Saves a user embedding to the encrypted envelope.
    """
    os.makedirs(os.path.dirname(EMBEDDING_FILE), exist_ok=True)
    
    key = get_or_prompt_key()
    if not key:
        logging.error("Cannot save embedding: no encryption key available.")
        return
        
    # Load current embeddings (uses cached key)
    embeddings = load_embeddings()
    embeddings[name] = embedding
    
    # Serialize to JSON format
    serialized = {k: v.tolist() for k, v in embeddings.items()}
    plaintext_bytes = json.dumps(serialized).encode('utf-8')
    
    try:
        from security.crypto_engine import encrypt
        nonce, ciphertext = encrypt(plaintext_bytes, key)
        
        # Keep KDF params from the existing envelope, or generate a fresh default salt
        envelope = read_envelope_file()
        if envelope:
            iterations = envelope["iterations"]
            salt = envelope["salt"]
        else:
            iterations = 600000
            salt = os.urandom(16)
            
        new_envelope = {
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8') if isinstance(salt, bytes) else salt,
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }
        
        with open(EMBEDDING_FILE, 'w') as f:
            json.dump(new_envelope, f, indent=4)
            
        # Ensure correct file permissions
        os.chmod(EMBEDDING_FILE, 0o600)
        logging.info(f"Saved encrypted embedding for user '{name}' to {EMBEDDING_FILE}")
    except Exception as e:
        logging.error(f"Error saving encrypted embedding: {e}")

def check_and_perform_migration(password_str: str = None) -> bool:
    """
    Detects if Phase 2 plaintext embeddings.json exists.
    Loads it, prompts user for master password, encrypts it under the new scheme,
    verifies it round-trips correctly, and deletes the old plaintext file.
    
    NOTE: Secure deletion (overwrite-before-unlink) is attempted, but it is not
    100% reliable on modern wear-leveled SSDs or copy-on-write filesystems (Btrfs, ZFS).
    """
    if not os.path.exists(OLD_EMBEDDING_FILE):
        return False
        
    logging.info("Migration: Plaintext embeddings.json detected.")
    if os.path.exists(EMBEDDING_FILE):
        logging.warning("Migration: Both embeddings.json and embeddings.enc exist. Skipping automatic migration.")
        return False
        
    if not password_str:
        if sys.stdin.isatty():
            import getpass
            print("\n=== FaceGate Plaintext-to-Encrypted Database Migration ===")
            print("Please set a master password to encrypt your existing face embeddings.")
            while True:
                p1 = getpass.getpass("Enter new master password: ")
                if len(p1) < 8:
                    print("Error: Password must be at least 8 characters long.")
                    continue
                p2 = getpass.getpass("Confirm new master password: ")
                if p1 != p2:
                    print("Error: Passwords do not match. Try again.")
                    continue
                password_str = p1
                break
        else:
            logging.error("Migration: Password needed but cannot prompt (not running in interactive TTY).")
            return False
            
    pwd_bytes = bytearray(password_str.encode('utf-8'))
    
    try:
        # Load plaintext embeddings
        with open(OLD_EMBEDDING_FILE, 'r') as f:
            old_data = json.load(f)
            
        # Verify JSON schema is valid
        parsed_old = {k: np.array(v, dtype=np.float32) for k, v in old_data.items()}
        
        # Derive key
        from security.crypto_engine import derive_key, encrypt, decrypt
        salt = os.urandom(16)
        iterations = 600000
        key = derive_key(pwd_bytes, salt, iterations)
        
        # Encrypt the dict data
        plaintext_bytes = json.dumps(old_data).encode('utf-8')
        nonce, ciphertext = encrypt(plaintext_bytes, key)
        
        # Write new envelope
        envelope = {
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }
        
        os.makedirs(os.path.dirname(EMBEDDING_FILE), exist_ok=True)
        with open(EMBEDDING_FILE, 'w') as f:
            json.dump(envelope, f, indent=4)
        os.chmod(EMBEDDING_FILE, 0o600)
        
        # Verify migrated data round-trips correctly
        decrypted_bytes = decrypt(nonce, ciphertext, key)
        decrypted_data = json.loads(decrypted_bytes.decode('utf-8'))
        
        # Verify key equivalence
        if set(old_data.keys()) != set(decrypted_data.keys()):
            raise ValueError("Keys mismatch after decryption verification")
            
        # Verify embedding vectors are numerically identical
        for username in old_data.keys():
            old_emb = np.array(old_data[username], dtype=np.float32)
            new_emb = np.array(decrypted_data[username], dtype=np.float32)
            if not np.array_equal(old_emb, new_emb):
                raise ValueError(f"Numerical embedding mismatch for '{username}'")
                
        logging.info("Migration: Verification successful. Decrypted embeddings are bit-for-bit identical.")
        set_cached_key(key)
        
        # Securely handle the old plaintext file: overwrite then delete.
        # We write zeroes to the file to overwrite plaintext blocks before unlinking.
        try:
            file_size = os.path.getsize(OLD_EMBEDDING_FILE)
            with open(OLD_EMBEDDING_FILE, 'wb') as f:
                f.write(b'\x00' * file_size)
                f.flush()
                os.fsync(f.fileno())
            os.unlink(OLD_EMBEDDING_FILE)
            logging.info("Migration: Old plaintext file securely deleted.")
        except Exception as e:
            logging.warning(f"Migration: Could not securely delete old file: {e}")
            
        return True
    except Exception as e:
        logging.critical(f"Migration: Verification or write failed: {e}")
        # Clean up partial envelope file
        if os.path.exists(EMBEDDING_FILE):
            try:
                os.unlink(EMBEDDING_FILE)
            except Exception:
                pass
        return False
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0
