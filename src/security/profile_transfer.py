import os
import sys
import json
import base64
import time
import platform
import hashlib
import getpass
import logging
import numpy as np

from security.crypto_engine import derive_key, encrypt, decrypt, build_aad
from database.embedding_store import load_embeddings, save_embedding, get_or_prompt_key

BUNDLE_FORMAT_ID = "facegate_profile_transfer"
MIN_PASSPHRASE_LEN = 8

def export_profile(output_path: str, export_users: list[str] = None, passphrase: str = None) -> tuple[int, str]:
    """
    Exports enrolled face profiles to an encrypted transfer bundle (.fgxfer).
    Re-encrypts embeddings under a fresh, one-time transfer passphrase with PBKDF2 (600k) + AES-256-GCM.
    
    Security note: Callers (CLI/GUI) MUST verify admin authentication (via verify_admin_face or
    master password verification) before invoking this function.
    """
    all_embeddings = load_embeddings()
    if not all_embeddings:
        raise ValueError("No enrolled face profiles found to export.")

    if export_users:
        target_embeddings = {}
        for u in export_users:
            if u not in all_embeddings:
                raise ValueError(f"Cannot export user '{u}': User is not enrolled in database.")
            target_embeddings[u] = all_embeddings[u]
    else:
        target_embeddings = all_embeddings

    if not passphrase:
        if sys.stdin.isatty():
            print("\n=== FaceGate Profile Export ===")
            print("Set a one-time transfer passphrase to protect this export file.")
            while True:
                p1 = getpass.getpass("Enter transfer passphrase: ")
                if len(p1) < MIN_PASSPHRASE_LEN:
                    print(f"Error: Passphrase must be at least {MIN_PASSPHRASE_LEN} characters long.")
                    continue
                p2 = getpass.getpass("Confirm transfer passphrase: ")
                if p1 != p2:
                    print("Error: Passphrases do not match. Try again.")
                    continue
                passphrase = p1
                break
        else:
            raise ValueError("Passphrase required for profile export in non-interactive mode.")

    if len(passphrase) < MIN_PASSPHRASE_LEN:
        raise ValueError(f"Passphrase must be at least {MIN_PASSPHRASE_LEN} characters long.")

    pwd_bytes = bytearray(passphrase.encode('utf-8'))
    try:
        salt = os.urandom(16)
        iterations = 600000
        transfer_key = derive_key(pwd_bytes, salt, iterations)

        serialized = {k: v.tolist() for k, v in target_embeddings.items()}
        json_payload_bytes = json.dumps(serialized, sort_keys=True).encode('utf-8')
        payload_checksum = hashlib.sha256(json_payload_bytes).hexdigest()

        payload_obj = {
            "embeddings": serialized,
            "checksum": payload_checksum
        }
        plaintext_bytes = json.dumps(payload_obj).encode('utf-8')

        aad = build_aad("pbkdf2_hmac_sha256", iterations, salt)
        nonce, ciphertext = encrypt(plaintext_bytes, transfer_key, aad)

        bundle = {
            "header": {
                "format": BUNDLE_FORMAT_ID,
                "version": "1.0",
                "source_host": platform.node(),
                "timestamp": time.time(),
                "users": list(target_embeddings.keys())
            },
            "kdf": "pbkdf2_hmac_sha256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8')
        }

        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir:
            os.makedirs(output_dir, mode=0o700, exist_ok=True)

        tmp_path = output_path + ".tmp"
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(bundle, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, output_path)
        logging.info(f"Successfully exported {len(target_embeddings)} profile(s) to {output_path}")
        return len(target_embeddings), output_path
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0

def read_profile_header(import_path: str) -> dict:
    """
    Reads unencrypted header metadata from a profile transfer file (.fgxfer).
    """
    if not os.path.exists(import_path):
        raise FileNotFoundError(f"Transfer file '{import_path}' does not exist.")

    with open(import_path, 'r') as f:
        bundle = json.load(f)

    header = bundle.get("header")
    if not header or header.get("format") != BUNDLE_FORMAT_ID:
        raise ValueError(f"Invalid transfer file format in '{import_path}'.")

    return header

def import_profile(import_path: str, passphrase: str = None, force_import: bool = False) -> list[str]:
    """
    Imports face profiles from an encrypted transfer file (.fgxfer).
    Requires the destination machine's master vault key to be available.
    
    Security note: Callers (CLI/GUI) MUST verify admin authentication (via verify_admin_face or
    master password verification) before invoking this function.
    """
    destination_key = get_or_prompt_key()
    if not destination_key:
        raise RuntimeError("Destination vault is locked. Master password required to import profiles.")

    header = read_profile_header(import_path)

    with open(import_path, 'r') as f:
        bundle = json.load(f)

    if not passphrase:
        if sys.stdin.isatty():
            print(f"\n=== FaceGate Profile Import ===")
            print(f"Source Machine : {header.get('source_host', 'unknown')}")
            print(f"Export Users   : {', '.join(header.get('users', []))}")
            passphrase = getpass.getpass("Enter transfer passphrase: ")
        else:
            raise ValueError("Passphrase required for profile import in non-interactive mode.")

    pwd_bytes = bytearray(passphrase.encode('utf-8'))
    try:
        salt = base64.b64decode(bundle["salt"])
        iterations = int(bundle["iterations"])
        nonce = base64.b64decode(bundle["nonce"])
        ciphertext = base64.b64decode(bundle["ciphertext"])
        kdf_name = bundle.get("kdf", "pbkdf2_hmac_sha256")

        transfer_key = derive_key(pwd_bytes, salt, iterations)
        aad = build_aad(kdf_name, iterations, salt)
        decrypted_bytes = decrypt(nonce, ciphertext, transfer_key, aad)
        payload = json.loads(decrypted_bytes.decode('utf-8'))

        imported_raw_embeddings = payload["embeddings"]
        expected_checksum = payload.get("checksum")

        # Verify payload checksum
        verify_bytes = json.dumps(imported_raw_embeddings, sort_keys=True).encode('utf-8')
        actual_checksum = hashlib.sha256(verify_bytes).hexdigest()
        if expected_checksum and actual_checksum != expected_checksum:
            raise ValueError("Integrity check failed: payload checksum mismatch.")

        local_embeddings = load_embeddings()
        imported_users = []

        for username, emb_list in imported_raw_embeddings.items():
            new_emb = np.array(emb_list, dtype=np.float32)

            if username in local_embeddings:
                existing_emb = local_embeddings[username]
                if np.array_equal(existing_emb, new_emb):
                    logging.info(f"User '{username}' embedding is identical to local profile. Skipping.")
                    continue
                elif not force_import:
                    raise ValueError(
                        f"User '{username}' already exists locally with a different face embedding. "
                        f"Use --force-import to overwrite."
                    )

            save_embedding(username, new_emb)
            imported_users.append(username)
            logging.info(f"Successfully imported profile for user '{username}'.")

        return imported_users
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0
