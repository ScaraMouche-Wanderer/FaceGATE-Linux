import os
import sys
import json
import base64
import logging
import numpy as np

EMBEDDING_FILE = os.path.expanduser("~/.config/facegate/embeddings.enc")
OLD_EMBEDDING_FILE = os.path.expanduser("~/.config/facegate/embeddings.json")

_cached_key = None

def _get_ram_key_file() -> str:
    uid = os.getuid()
    run_dir = f"/run/user/{uid}"
    if os.path.exists(run_dir):
        return os.path.join(run_dir, "facegate.key")
    # Fallback to tempdir if /run/user/{uid} is not available
    import tempfile
    return os.path.join(tempfile.gettempdir(), f".facegate_{uid}.key")

def set_cached_key(key: bytes):
    """
    Caches the derived key in process memory and user RAM tmpfs (/run/user/{uid}/facegate.key).
    """
    global _cached_key
    _cached_key = bytearray(key) if isinstance(key, bytes) else key

    # Write key to user-private RAM-backed tmpfs file (0600 permissions)
    try:
        ram_file = _get_ram_key_file()
        key_bytes = bytes(key) if isinstance(key, (bytes, bytearray)) else key
        with open(ram_file, 'wb') as f:
            f.write(key_bytes)
        os.chmod(ram_file, 0o600)
    except Exception as e:
        logging.warning(f"Could not persist RAM key file: {e}")

def get_cached_key() -> bytes:
    """
    Retrieves the cached key from process memory or user RAM tmpfs.
    """
    global _cached_key
    if _cached_key:
        return bytes(_cached_key)

    # Check RAM tmpfs file
    try:
        ram_file = _get_ram_key_file()
        if os.path.exists(ram_file):
            with open(ram_file, 'rb') as f:
                data = f.read()
                if len(data) == 32:
                    _cached_key = bytearray(data)
                    return bytes(_cached_key)
    except Exception as e:
        logging.error(f"Error reading RAM key file: {e}")

    return None

def clear_cached_key():
    """
    Securely zeroes and removes the cached key from memory and RAM tmpfs.
    """
    global _cached_key
    if _cached_key is not None:
        for i in range(len(_cached_key)):
            _cached_key[i] = 0
        _cached_key = None

    try:
        ram_file = _get_ram_key_file()
        if os.path.exists(ram_file):
            with open(ram_file, 'wb') as f:
                f.write(b'\x00' * 32)
            os.remove(ram_file)
    except Exception:
        pass

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
    Retrieves the cached encryption key if available.

    This function does NOT use any hardcoded default password. If the daemon
    has not been unlocked via proper password authentication, it returns None.
    Callers must handle the locked (None) state gracefully — typically by
    falling back to a password-only auth dialog.

    The master password must be set via `--set-master-password` or the
    Enrollment Wizard before face recognition can function.
    """
    key = get_cached_key()
    if key:
        return key

    # No cached key available — daemon is in locked state.
    # The caller (auth dialog, IPC service) must prompt the user for
    # their master password to unlock. We never silently create or
    # reset the encrypted database.
    if not os.path.exists(EMBEDDING_FILE):
        logging.warning(
            "No encrypted embedding store found. "
            "Please run 'facegate --set-master-password' to initialize."
        )
    else:
        logging.info(
            "Encrypted embedding store exists but no key is cached. "
            "Master password entry required to unlock."
        )
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
            from utils.config_loader import get_config
            config = get_config()
            iterations = int(config.get("security.pbkdf2_iterations", 600000))
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

def get_admin_user() -> str | None:
    """
    Returns the designated Admin User username.
    If explicitly configured in security.admin_user, returns that user.
    Otherwise, defaults to the first enrolled user in the store.
    """
    from utils.config_loader import get_config
    config = get_config()
    admin_cfg = config.get("security.admin_user")
    
    embeddings = load_embeddings()
    if not embeddings:
        return None
        
    if admin_cfg and admin_cfg in embeddings:
        return admin_cfg
        
    first_user = list(embeddings.keys())[0]
    return first_user

def set_admin_user(name: str):
    """
    Designates a specific enrolled user as the Primary Admin.
    """
    embeddings = load_embeddings()
    if name not in embeddings:
        raise ValueError(f"Cannot designate '{name}' as admin: User is not enrolled.")
        
    from utils.config_loader import get_config
    config = get_config()
    config.set("security.admin_user", name)
    config.save()
    logging.info(f"User '{name}' designated as Primary Admin.")

def delete_embedding(name: str):
    """
    Removes a user embedding from the encrypted envelope.
    Loads all embeddings, removes the specified user, re-encrypts, and saves.
    Raises ValueError if the user is not found.
    """
    key = get_or_prompt_key()
    if not key:
        raise RuntimeError("Cannot delete embedding: no encryption key available.")
    
    embeddings = load_embeddings()
    if name not in embeddings:
        raise ValueError(f"User '{name}' is not enrolled in the database.")
    
    del embeddings[name]
    
    # Re-serialize and re-encrypt
    serialized = {k: v.tolist() for k, v in embeddings.items()}
    plaintext_bytes = json.dumps(serialized).encode('utf-8')
    
    try:
        from security.crypto_engine import encrypt
        nonce, ciphertext = encrypt(plaintext_bytes, key)
        
        envelope = read_envelope_file()
        if envelope:
            iterations = envelope["iterations"]
            salt = envelope["salt"]
        else:
            from utils.config_loader import get_config
            config = get_config()
            iterations = int(config.get("security.pbkdf2_iterations", 600000))
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
            
        os.chmod(EMBEDDING_FILE, 0o600)
        logging.info(f"Deleted embedding for user '{name}' from {EMBEDDING_FILE}. {len(embeddings)} user(s) remaining.")

        # Handle Admin User re-assignment if the deleted user was the admin
        from utils.config_loader import get_config
        config = get_config()
        if config.get("security.admin_user") == name or get_admin_user() == name:
            if embeddings:
                next_admin = list(embeddings.keys())[0]
                config.set("security.admin_user", next_admin)
            else:
                config.set("security.admin_user", None)
            config.save()

        # Notify running daemon via D-Bus session bus
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
                if interface.isValid():
                    interface.call("RemoveEnrolledUser", name)
        except Exception as ex:
            logging.warning(f"Could not sync embedding deletion with daemon over D-Bus: {ex}")
    except Exception as e:
        logging.error(f"Error deleting encrypted embedding: {e}")
        raise

def check_and_perform_migration(password_str: str = None) -> bool:
    """
    Detects if plaintext embeddings.json exists.
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
        from utils.config_loader import get_config
        config = get_config()
        salt = os.urandom(16)
        iterations = int(config.get("security.pbkdf2_iterations", 600000))
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
            old_emb = parsed_old[username]
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
