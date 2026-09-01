import os
import sys
import json
import pytest
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from security.profile_transfer import (
    export_profile, import_profile, read_profile_header
)
import database.embedding_store as embedding_store

@pytest.fixture
def setup_test_vault(tmp_path, monkeypatch):
    """
    Sets up a temporary test embedding store and cached vault key.
    """
    enc_path = str(tmp_path / "embeddings.enc")
    monkeypatch.setattr(embedding_store, "EMBEDDING_FILE", enc_path)
    
    test_key = b"\x42" * 32
    monkeypatch.setattr(embedding_store, "_cached_key", bytearray(test_key))
    monkeypatch.setattr(embedding_store, "get_or_prompt_key", lambda: test_key)
    monkeypatch.setattr(embedding_store, "get_cached_key", lambda: test_key)
    
    # Save test embeddings
    user1_emb = np.random.randn(512).astype(np.float32)
    user2_emb = np.random.randn(512).astype(np.float32)
    
    embedding_store.save_embedding("alice", user1_emb)
    embedding_store.save_embedding("bob", user2_emb)
    
    return {
        "enc_path": enc_path,
        "key": test_key,
        "alice": user1_emb,
        "bob": user2_emb
    }

def test_export_and_import_roundtrip(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_transfer.fgxfer")
    passphrase = "SecretTransferPassphrase123!"

    count, path = export_profile(export_file, passphrase=passphrase)
    assert count == 2
    assert os.path.exists(export_file)

    # Read header without passphrase
    header = read_profile_header(export_file)
    assert header["format"] == "facegate_profile_transfer"
    assert "alice" in header["users"]
    assert "bob" in header["users"]

    # Clear bob from local vault to test re-importing bob
    embedding_store.delete_embedding("bob")
    assert "bob" not in embedding_store.load_embeddings()

    # Import bob back
    imported_users = import_profile(export_file, passphrase=passphrase)
    assert "bob" in imported_users

    restored = embedding_store.load_embeddings()
    assert "bob" in restored
    assert np.allclose(restored["bob"], setup_test_vault["bob"])

def test_wrong_passphrase_rejection(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_wrong_pwd.fgxfer")
    export_profile(export_file, passphrase="ValidPassphrase123!")

    with pytest.raises(Exception): # AES-GCM tag check or JSON decode fails
        import_profile(export_file, passphrase="WrongPassphrase456!")

def test_short_passphrase_rejection(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_short.fgxfer")
    with pytest.raises(ValueError, match="at least 8 characters"):
        export_profile(export_file, passphrase="short")

def test_unknown_user_export_rejection(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_unknown.fgxfer")
    with pytest.raises(ValueError, match="is not enrolled"):
        export_profile(export_file, export_users=["charlie"], passphrase="ValidPassphrase123!")

def test_ciphertext_tamper_rejection(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_tampered.fgxfer")
    passphrase = "ValidPassphrase123!"
    export_profile(export_file, passphrase=passphrase)

    # Tamper with file ciphertext
    with open(export_file, "r") as f:
        bundle = json.load(f)

    # Modify raw ciphertext
    raw_ct = list(bundle["ciphertext"])
    raw_ct[0] = "A" if raw_ct[0] != "A" else "B"
    bundle["ciphertext"] = "".join(raw_ct)

    with open(export_file, "w") as f:
        json.dump(bundle, f)

    with pytest.raises(Exception):
        import_profile(export_file, passphrase=passphrase)

def test_import_collision_protection(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_collision.fgxfer")
    passphrase = "ValidPassphrase123!"
    export_profile(export_file, export_users=["alice"], passphrase=passphrase)

    # Modify alice's embedding locally to create a collision
    different_emb = np.random.randn(512).astype(np.float32)
    embedding_store.save_embedding("alice", different_emb)

    # Import without force should fail
    with pytest.raises(ValueError, match="already exists locally with a different face embedding"):
        import_profile(export_file, passphrase=passphrase, force_import=False)

    # Import with force should succeed and overwrite
    imported = import_profile(export_file, passphrase=passphrase, force_import=True)
    assert "alice" in imported

    restored = embedding_store.load_embeddings()
    assert np.allclose(restored["alice"], setup_test_vault["alice"])

def test_import_idempotent(setup_test_vault, tmp_path):
    export_file = str(tmp_path / "test_idempotent.fgxfer")
    passphrase = "ValidPassphrase123!"
    export_profile(export_file, passphrase=passphrase)

    # Re-importing exact same embedding is a no-op
    imported = import_profile(export_file, passphrase=passphrase, force_import=False)
    assert imported == []
