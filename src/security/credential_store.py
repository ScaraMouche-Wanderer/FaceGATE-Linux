import sys
import os
import json
import logging
import base64
from security.crypto_engine import derive_key, encrypt, decrypt
from database.embedding_store import (
    EMBEDDING_FILE, OLD_EMBEDDING_FILE, read_envelope_file,
    set_cached_key, check_and_perform_migration
)

def verify_password(password: str) -> bool:
    """
    Verifies the password by trying to decrypt the embeddings envelope.
    If decryption succeeds, caches the derived key and returns True.
    Ensures memory hygiene by converting to bytearray and zeroing it out.
    
    NOTE: Python's string immutability means a 'str'-typed password can linger
    in memory until garbage-collected. To minimize the window of exposure, we
    convert it to a bytearray and explicitly overwrite it as soon as key derivation
    is complete.
    """
    if not password:
        return False
        
    pwd_bytes = bytearray(password.encode('utf-8'))
    envelope = read_envelope_file()
    
    # If no envelope exists, but an old plaintext file does, perform migration in-place
    if not envelope:
        if os.path.exists(OLD_EMBEDDING_FILE):
            try:
                # Perform migration using the provided password
                success = check_and_perform_migration(password)
                if success:
                    # After successful migration, reading envelope should succeed
                    envelope = read_envelope_file()
                else:
                    return False
            except Exception as e:
                logging.error(f"Migration failed during password verification: {e}")
                return False
        else:
            logging.error("No credential envelope exists. Please set a master password first.")
            return False
            
    if not envelope:
        return False
        
    try:
        salt = envelope["salt"]
        iterations = envelope["iterations"]
        nonce = envelope["nonce"]
        ciphertext = envelope["ciphertext"]
        
        # Derive the AES key
        key = derive_key(pwd_bytes, salt, iterations)
        
        # Attempt to decrypt the embeddings with AAD binding.
        from security.crypto_engine import build_aad
        has_kdf = "kdf" in envelope
        aad = build_aad(envelope.get("kdf", "pbkdf2_hmac_sha256"), iterations, salt) if has_kdf else None
        try:
            decrypt(nonce, ciphertext, key, aad)
        except Exception:
            decrypt(nonce, ciphertext, key, aad=None)
        
        # Success! Cache the derived key
        set_cached_key(key)
        
        # Ensure we do not log the plaintext password, derived key, or embeddings
        logging.info("Credential check: SUCCESS")
        return True
    except Exception:
        logging.warning("Credential check: FAILURE (Incorrect password or corrupted store)")
        return False
    finally:
        # Zero out the password buffer in memory
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0

def update_master_password(current_password: str | None, new_password: str) -> None:
    """
    Core function to set or change the master password.
    If an envelope exists, it will attempt to decrypt it using current_password.
    If decryption succeeds (or if no envelope exists yet), it will encrypt
    the existing (or empty) database under new_password and save the new envelope.
    """
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    # 1. Check if a master password already exists
    envelope = read_envelope_file()
    existing_data = {}
    
    if envelope:
        if current_password is None:
            raise ValueError("Current password is required to change password.")
            
        current_bytes = bytearray(current_password.encode('utf-8'))
        try:
            salt = envelope["salt"]
            iterations = envelope["iterations"]
            nonce = envelope["nonce"]
            ciphertext = envelope["ciphertext"]
            
            key = derive_key(current_bytes, salt, iterations)
            from security.crypto_engine import build_aad
            has_kdf = "kdf" in envelope
            aad = build_aad(envelope.get("kdf", "pbkdf2_hmac_sha256"), iterations, salt) if has_kdf else None
            try:
                decrypted_bytes = decrypt(nonce, ciphertext, key, aad)
            except Exception:
                decrypted_bytes = decrypt(nonce, ciphertext, key, aad=None)
            existing_data = json.loads(decrypted_bytes.decode('utf-8'))
        except Exception:
            raise ValueError("Incorrect current master password.")
        finally:
            for i in range(len(current_bytes)):
                current_bytes[i] = 0

    pwd_bytes = bytearray(new_password.encode('utf-8'))
    try:
        from utils.config_loader import get_config
        config = get_config()
        salt = os.urandom(16)
        iterations = int(config.get("security.pbkdf2_iterations", 600000))
        new_key = derive_key(pwd_bytes, salt, iterations)
        
        plaintext_bytes = json.dumps(existing_data).encode('utf-8')
        from security.crypto_engine import build_aad
        aad = build_aad("pbkdf2_hmac_sha256", iterations, salt)
        nonce, ciphertext = encrypt(plaintext_bytes, new_key, aad)
        
        new_envelope = {
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }
        
        os.makedirs(os.path.dirname(EMBEDDING_FILE), exist_ok=True)
        tmp_file = EMBEDDING_FILE + ".tmp"
        with open(tmp_file, 'w') as f:
            json.dump(new_envelope, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
            
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, EMBEDDING_FILE)

        # Update in-memory key cache to match newly encrypted envelope
        set_cached_key(new_key)
        logging.info("Updated in-memory encryption key cache after password change.")

        # Notify daemon to reload config (key is shared via RAM tmpfs file).
        # Removed UpdateCachedKey D-Bus call for security — see audit §1.2.
        # The daemon's get_cached_key() will read the updated key from the RAM file.
        from database.embedding_store import notify_daemon_reload
        notify_daemon_reload()
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0

def set_master_password_cli():
    """
    CLI interface to set or change the FaceGate master password.
    Supports first-run setup, changing an existing password, and migrations.
    """
    import getpass
    
    print("\n==========================================")
    print("      FaceGate Master Password Setup      ")
    print("==========================================\n")
    
    # 1. Detect if migration is needed
    if os.path.exists(OLD_EMBEDDING_FILE) and not os.path.exists(EMBEDDING_FILE):
        print("Plaintext embeddings.json detected. Performing migration.")
        check_and_perform_migration()
        return

    # 2. Check if a master password already exists
    envelope = read_envelope_file()
    current_pwd = None
    
    if envelope:
        print("An encrypted embeddings store already exists.")
        current_pwd = getpass.getpass("Enter current master password: ")

    # 3. Prompt for the new master password
    while True:
        p1 = getpass.getpass("Enter new master password: ")
        if len(p1) < 8:
            print("Error: Password must be at least 8 characters long.")
            continue
            
        p2 = getpass.getpass("Confirm new master password: ")
        if p1 != p2:
            print("Error: Passwords do not match. Try again.")
            continue
            
        new_pwd = p1
        break

    try:
        update_master_password(current_pwd, new_pwd)
        print("SUCCESS: Master password configured. Embeddings store encrypted at rest.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
