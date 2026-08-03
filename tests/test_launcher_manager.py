import os
import sys
import json
import pytest
import time
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from locking.launcher_manager import (
    LauncherManager,
    atomic_write,
    calculate_checksum,
    calculate_content_checksum,
    is_facegate_launcher
)


def test_atomic_write_and_checksum(tmp_path):
    target = str(tmp_path / "test_file.txt")
    content = "Hello, FaceGate Atomic Write!"

    assert atomic_write(target, content)
    assert os.path.exists(target)

    with open(target, 'r') as f:
        read_content = f.read()
    assert read_content == content

    checksum = calculate_checksum(target)
    expected_checksum = calculate_content_checksum(content)
    assert checksum == expected_checksum


def test_launcher_manager_backup_and_protect(tmp_path):
    user_desktop = str(tmp_path / "user_desktop")
    backup_dir = str(tmp_path / "backup")
    system_desktop = str(tmp_path / "system_desktop")
    manifest_file = str(tmp_path / "manifest.json")

    os.makedirs(system_desktop, exist_ok=True)
    orig_content = "[Desktop Entry]\nName=Test App\nExec=kitty --foo\nType=Application\n"
    sys_file = os.path.join(system_desktop, "test_app.desktop")
    with open(sys_file, "w") as f:
        f.write(orig_content)

    manager = LauncherManager(
        user_desktop_dir=user_desktop,
        backup_dir=backup_dir,
        manifest_file=manifest_file
    )

    with patch("locking.launcher_manager.SYSTEM_DESKTOP_DIRS", [system_desktop]):
        # Protect app
        app_info = {"desktop_name": "test_app.desktop", "id": "kitty"}
        success = manager.protect_application(app_info)
        assert success

        user_file = os.path.join(user_desktop, "test_app.desktop")
        backup_file = os.path.join(backup_dir, "test_app.desktop")

        assert os.path.exists(user_file)
        assert os.path.exists(backup_file)

        # Verify backup stores EXACT original contents
        with open(backup_file, "r") as f:
            backed_up_content = f.read()
        assert backed_up_content == orig_content

        # Verify modified launcher has FaceGate marker & --auth-launch wrapper
        assert is_facegate_launcher(user_file)

        # Verify manifest contains index details
        manifest = manager.load_manifest()
        assert "test_app.desktop" in manifest
        info = manifest["test_app.desktop"]
        assert info["protected"] is True
        assert info["original_exec"] == "kitty --foo"
        assert info["original_checksum"] == calculate_content_checksum(orig_content)
        assert info["timestamp"] > 0


def test_launcher_manager_unprotect_and_restore(tmp_path):
    user_desktop = str(tmp_path / "user_desktop")
    backup_dir = str(tmp_path / "backup")
    system_desktop = str(tmp_path / "system_desktop")
    manifest_file = str(tmp_path / "manifest.json")

    os.makedirs(system_desktop, exist_ok=True)
    orig_content = "[Desktop Entry]\nName=Test App 2\nExec=ls -l\n"
    sys_file = os.path.join(system_desktop, "app2.desktop")
    with open(sys_file, "w") as f:
        f.write(orig_content)

    manager = LauncherManager(
        user_desktop_dir=user_desktop,
        backup_dir=backup_dir,
        manifest_file=manifest_file
    )

    with patch("locking.launcher_manager.SYSTEM_DESKTOP_DIRS", [system_desktop]):
        manager.protect_application({"desktop_name": "app2.desktop"})
        user_file = os.path.join(user_desktop, "app2.desktop")
        assert os.path.exists(user_file)

        # Unprotect/Restore app
        restored = manager.unprotect_application("app2.desktop")
        assert restored

        # Shadow file removed, system default restored
        assert not os.path.exists(user_file)

        manifest = manager.load_manifest()
        assert manifest["app2.desktop"]["protected"] is False


def test_startup_recovery(tmp_path):
    user_desktop = str(tmp_path / "user_desktop")
    backup_dir = str(tmp_path / "backup")
    system_desktop = str(tmp_path / "system_desktop")
    manifest_file = str(tmp_path / "manifest.json")

    os.makedirs(system_desktop, exist_ok=True)
    sys_file = os.path.join(system_desktop, "abandoned.desktop")
    with open(sys_file, "w") as f:
        f.write("[Desktop Entry]\nExec=echo hello\n")

    manager = LauncherManager(
        user_desktop_dir=user_desktop,
        backup_dir=backup_dir,
        manifest_file=manifest_file
    )

    with patch("locking.launcher_manager.SYSTEM_DESKTOP_DIRS", [system_desktop]):
        manager.protect_application({"desktop_name": "abandoned.desktop"})
        user_file = os.path.join(user_desktop, "abandoned.desktop")
        assert is_facegate_launcher(user_file)

        # Simulate startup recovery where 'abandoned.desktop' is NOT in protected_apps
        protected_apps = []  # Empty protected apps list
        recovered_count = manager.startup_recovery(protected_apps)
        assert recovered_count == 1
        assert not os.path.exists(user_file)


def test_verify_launcher(tmp_path):
    valid_file = str(tmp_path / "valid.desktop")
    atomic_write(valid_file, "[Desktop Entry]\nExec=ls -la\n")

    manager = LauncherManager()
    assert manager.verify_launcher(valid_file)

    invalid_file = str(tmp_path / "invalid.desktop")
    atomic_write(invalid_file, "[Desktop Entry]\nNoExecHere=1\n")
    assert not manager.verify_launcher(invalid_file)
