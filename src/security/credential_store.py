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
        
        # Attempt to decrypt the embeddings.
        # This will raise cryptography.exceptions.InvalidTag on wrong key.
        decrypted_bytes = decrypt(nonce, ciphertext, key)
        
        # Success! Cache the derived key
        set_cached_key(key)
        
        # Ensure we do not log the plaintext password, derived key, or embeddings
        logging.info("Credential check: SUCCESS")
        return True
    except Exception as e:
        logging.warning("Credential check: FAILURE (Incorrect password or corrupted store)")
        return False
    finally:
        # Zero out the password buffer in memory
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
        # Trigger migration flow (will prompt internally for a password if none given)
        check_and_perform_migration()
        return

    # 2. Check if a master password already exists
    envelope = read_envelope_file()
    existing_data = {}
    
    if envelope:
        print("An encrypted embeddings store already exists.")
        current_pwd = getpass.getpass("Enter current master password: ")
        current_bytes = bytearray(current_pwd.encode('utf-8'))
        
        try:
            salt = envelope["salt"]
            iterations = envelope["iterations"]
            nonce = envelope["nonce"]
            ciphertext = envelope["ciphertext"]
            
            key = derive_key(current_bytes, salt, iterations)
            decrypted_bytes = decrypt(nonce, ciphertext, key)
            existing_data = json.loads(decrypted_bytes.decode('utf-8'))
            print("Current password verified successfully.\n")
        except Exception:
            print("Error: Incorrect current master password.", file=sys.stderr)
            sys.exit(1)
        finally:
            for i in range(len(current_bytes)):
                current_bytes[i] = 0

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
            
        new_password = p1
        break
        
    pwd_bytes = bytearray(new_password.encode('utf-8'))
    
    try:
        # Derive key with fresh salt and OWASP iteration count (600,000)
        salt = os.urandom(16)
        iterations = 600000
        new_key = derive_key(pwd_bytes, salt, iterations)
        
        # Encrypt the database contents (either existing_data or an empty dict)
        plaintext_bytes = json.dumps(existing_data).encode('utf-8')
        nonce, ciphertext = encrypt(plaintext_bytes, new_key)
        
        # Prepare envelope
        new_envelope = {
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }
        
        # Write to file
        os.makedirs(os.path.dirname(EMBEDDING_FILE), exist_ok=True)
        with open(EMBEDDING_FILE, 'w') as f:
            json.dump(new_envelope, f, indent=4)
            
        # Enforce file permissions
        os.chmod(EMBEDDING_FILE, 0o600)
        
        print("SUCCESS: Master password configured. Embeddings store encrypted at rest.")
    except Exception as e:
        print(f"Error: Failed to encrypt or write credentials envelope: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0
