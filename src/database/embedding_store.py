import os
import sys
import json
import base64
import logging
import numpy as np

EMBEDDING_FILE = os.path.expanduser("~/.config/facegate/embeddings.enc")
OLD_EMBEDDING_FILE = os.path.expanduser("~/.config/facegate/embeddings.json")

import threading
_cached_key = None
_cached_key_lock = threading.Lock()

def _get_ram_key_file() -> str:
    uid = os.getuid()
    run_dir = f"/run/user/{uid}"
    if os.path.exists(run_dir):
        return os.path.join(run_dir, "facegate.key")
    # Fallback to private 0700 user directory instead of world-writable /tmp
    fallback_dir = os.path.expanduser("~/.config/facegate/.runtime")
    os.makedirs(fallback_dir, mode=0o700, exist_ok=True)
    os.chmod(fallback_dir, 0o700)
    return os.path.join(fallback_dir, "facegate.key")

def _get_machine_bound_key() -> bytes:
    """
    Derives a machine-and-user-bound master key for local vault key encryption.
    """
    import hashlib
    machine_id = ""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    machine_id = f.read().strip()
                if machine_id:
                    break
            except Exception:
                pass
    if not machine_id:
        machine_id = "facegate-fallback-machine-id"

    seed = f"facegate:{machine_id}:{os.getuid()}:{os.path.expanduser('~')}".encode('utf-8')
    from security.crypto_engine import derive_key
    salt = b"facegate-vault-salt-v1"
    return derive_key(seed, salt, iterations=10000)

def _save_persistent_vault_key(key: bytes):
    """
    Saves the derived key to OS keyring if security.persist_vault_key is explicitly enabled.
    By default (persist_vault_key=False), keys are kept strictly in RAM and session tmpfs.
    """
    from utils.config_loader import get_config
    try:
        config = get_config()
        if not config.get("security.persist_vault_key", False):
            logging.debug("Persistent vault key storage disabled by default config (security.persist_vault_key=false).")
            return
    except Exception:
        return

    key_bytes = bytes(key) if isinstance(key, (bytes, bytearray)) else key

    # Save to system keyring if keyring module is available
    try:
        import keyring
        keyring.set_password("facegate", "vault_key", key_bytes.hex())
        logging.info("Saved vault encryption key to system keyring.")
    except Exception as e:
        logging.warning(f"System keyring save skipped/failed: {e}")

def _load_persistent_vault_key() -> bytes | None:
    """
    Attempts to restore the vault key from system keyring if security.persist_vault_key is enabled.
    """
    from utils.config_loader import get_config
    try:
        config = get_config()
        if not config.get("security.persist_vault_key", False):
            return None
    except Exception:
        return None

    # Try system keyring
    try:
        import keyring
        val = keyring.get_password("facegate", "vault_key")
        if val:
            b = bytes.fromhex(val)
            if len(b) == 32:
                logging.info("Restored vault encryption key from system keyring.")
                return b
    except Exception as e:
        logging.debug(f"System keyring lookup skipped: {e}")

    return None

def set_cached_key(key: bytes):
    """
    Caches the derived key in process memory, user RAM tmpfs, system keyring, and machine-bound storage.
    """
    global _cached_key
    with _cached_key_lock:
        _cached_key = bytearray(key) if isinstance(key, bytes) else key

    # Write key to user-private RAM-backed tmpfs file (0600 permissions).
    try:
        ram_file = _get_ram_key_file()
        key_bytes = bytes(key) if isinstance(key, (bytes, bytearray)) else key
        fd = os.open(ram_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(key_bytes)
        os.chmod(ram_file, 0o600)
    except Exception as e:
        logging.warning(f"Could not persist RAM key file: {e}")

    # Save to persistent storage (system keyring / machine-bound file)
    _save_persistent_vault_key(key)

def get_cached_key() -> bytes:
    """
    Retrieves the cached key from process memory, user RAM tmpfs, or persistent storage.
    """
    global _cached_key
    with _cached_key_lock:
        if _cached_key:
            return bytes(_cached_key)

    # Check RAM tmpfs file
    try:
        ram_file = _get_ram_key_file()
        if os.path.exists(ram_file):
            with open(ram_file, 'rb') as f:
                data = f.read()
                if len(data) == 32:
                    with _cached_key_lock:
                        _cached_key = bytearray(data)
                    return bytes(data)
    except Exception as e:
        logging.error(f"Error reading RAM key file: {e}")

    # Check persistent storage (system keyring / machine-bound file)
    p_key = _load_persistent_vault_key()
    if p_key:
        with _cached_key_lock:
            _cached_key = bytearray(p_key)
        # Also sync to RAM tmpfs file for fast IPC access
        try:
            ram_file = _get_ram_key_file()
            fd = os.open(ram_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(p_key)
            os.chmod(ram_file, 0o600)
        except Exception:
            pass
        return p_key

    return None

def clear_cached_key():
    """
    Securely zeroes and removes the cached key from memory, RAM tmpfs, and persistent storage.
    """
    global _cached_key
    with _cached_key_lock:
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

    try:
        import keyring
        keyring.delete_password("facegate", "vault_key")
    except Exception:
        pass

    try:
        vault_key_file = os.path.expanduser("~/.config/facegate/.vault_key.enc")
        if os.path.exists(vault_key_file):
            os.remove(vault_key_file)
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
            "kdf": envelope.get("kdf"),
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
        from security.crypto_engine import decrypt, build_aad
        has_kdf = "kdf" in envelope and envelope["kdf"] is not None
        if has_kdf:
            aad = build_aad(envelope["kdf"], envelope.get("iterations", 600000), envelope.get("salt", ""))
            decrypted_bytes = decrypt(envelope["nonce"], envelope["ciphertext"], key, aad)
        else:
            decrypted_bytes = decrypt(envelope["nonce"], envelope["ciphertext"], key, aad=None)
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
        raise RuntimeError("Cannot save embedding: no encryption key available.")
        
    # Load current embeddings (uses cached key)
    embeddings = load_embeddings()
    embeddings[name] = embedding
    
    # Serialize to JSON format
    serialized = {k: v.tolist() for k, v in embeddings.items()}
    plaintext_bytes = json.dumps(serialized).encode('utf-8')
    
    try:
        # Keep KDF params from the existing envelope, or generate a fresh default salt
        envelope = read_envelope_file()
        if envelope:
            iterations = envelope["iterations"]
            salt = envelope["salt"]
            kdf_name = envelope.get("kdf", "pbkdf2_hmac_sha256")
        else:
            from utils.config_loader import get_config
            config = get_config()
            iterations = int(config.get("security.pbkdf2_iterations", 600000))
            salt = os.urandom(16)
            kdf_name = "pbkdf2_hmac_sha256"

        from security.crypto_engine import encrypt, build_aad
        aad = build_aad(kdf_name, iterations, salt)
        nonce, ciphertext = encrypt(plaintext_bytes, key, aad)
            
        new_envelope = {
            "kdf": kdf_name,
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8') if isinstance(salt, bytes) else salt,
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }
        
        tmp_file = EMBEDDING_FILE + ".tmp"
        fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(new_envelope, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
            
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, EMBEDDING_FILE)
        logging.info(f"Saved encrypted embedding for user '{name}' to {EMBEDDING_FILE}")

        # Ensure Primary Admin is configured
        from utils.config_loader import get_config
        config = get_config()
        if not config.get("security.admin_user"):
            config.set("security.admin_user", name)
            config.save()

        # Signal running daemon to reload user embeddings safely
        notify_daemon_reload()

        # Write initialization sentinel (idempotent)
        from security.state_watchdog import write_sentinel
        write_sentinel()
    except Exception as e:
        logging.error(f"Error saving encrypted embedding: {e}")
        raise RuntimeError(f"Error saving encrypted embedding: {e}")

def notify_daemon_reload():
    """
    Safely notifies the FaceGate daemon to reload configuration.
    If running inside the daemon process itself, reloads in-process without D-Bus IPC.
    Otherwise, sends an asynchronous D-Bus signal cross-process.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return
            
        try:
            owner_reply = bus.interface().serviceOwner("org.facegate.FaceGate")
            if owner_reply.isValid() and owner_reply.value() == bus.baseService():
                app_inst = QApplication.instance()
                if hasattr(app_inst, "reload_config"):
                    app_inst.reload_config()
                return
        except Exception:
            pass

        interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
        if interface.isValid():
            interface.asyncCall("ReloadConfig")
    except Exception as e:
        logging.warning(f"Could not notify daemon of config reload: {e}")

def notify_daemon_user_removed(name: str):
    """
    Safely notifies the FaceGate daemon of an enrolled user deletion.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return
            
        try:
            owner_reply = bus.interface().serviceOwner("org.facegate.FaceGate")
            if owner_reply.isValid() and owner_reply.value() == bus.baseService():
                app_inst = QApplication.instance()
                if hasattr(app_inst, "reload_config"):
                    app_inst.reload_config()
                return
        except Exception:
            pass

        interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
        if interface.isValid():
            interface.asyncCall("RemoveEnrolledUser", name)
    except Exception as e:
        logging.warning(f"Could not sync embedding deletion with daemon over D-Bus: {e}")

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
        envelope = read_envelope_file()
        if envelope:
            iterations = envelope["iterations"]
            salt = envelope["salt"]
            kdf_name = envelope.get("kdf", "pbkdf2_hmac_sha256")
        else:
            from utils.config_loader import get_config
            config = get_config()
            iterations = int(config.get("security.pbkdf2_iterations", 600000))
            salt = os.urandom(16)
            kdf_name = "pbkdf2_hmac_sha256"

        from security.crypto_engine import encrypt, build_aad
        aad = build_aad(kdf_name, iterations, salt)
        nonce, ciphertext = encrypt(plaintext_bytes, key, aad)
        
        new_envelope = {
            "kdf": kdf_name,
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8') if isinstance(salt, bytes) else salt,
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }
        
        tmp_file = EMBEDDING_FILE + ".tmp"
        fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(new_envelope, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
            
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, EMBEDDING_FILE)
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

        # Notify running daemon via D-Bus session bus or in-process
        notify_daemon_user_removed(name)
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
        tmp_file = EMBEDDING_FILE + ".tmp"
        fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(envelope, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, EMBEDDING_FILE)
        
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
