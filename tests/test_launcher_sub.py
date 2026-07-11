import os
import sys
import pytest
import shutil
from unittest.mock import patch, MagicMock

# Ensure PySide6 QApplication is initialized for the test
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

def test_apply_substitution_success(tmp_path):
    from locking.launcher_sub import apply_substitution
    
    # Setup dummy paths
    user_desktop_dir = str(tmp_path / "user_desktop")
    backup_dir = str(tmp_path / "backup")
    system_desktop_dir = str(tmp_path / "system_desktop")
    
    os.makedirs(system_desktop_dir, exist_ok=True)
    
    # Create a dummy system .desktop file
    sys_file = os.path.join(system_desktop_dir, "test.desktop")
    with open(sys_file, "w") as f:
        f.write("[Desktop Entry]\nExec=kitty\n")
        
    with patch("locking.launcher_sub.USER_DESKTOP_DIR", user_desktop_dir), \
         patch("locking.launcher_sub.BACKUP_DIR", backup_dir), \
         patch("locking.launcher_sub.SYSTEM_DESKTOP_DIRS", [system_desktop_dir]):
         
         apply_substitution([{"desktop_name": "test.desktop"}])
         
         # Verify files are created
         user_file = os.path.join(user_desktop_dir, "test.desktop")
         backup_file = os.path.join(backup_dir, "test.desktop")
         assert os.path.exists(user_file)
         assert os.path.exists(backup_file)
         
         with open(user_file, "r") as f:
             content = f.read()
             assert "# Modified by FaceGate" in content
             assert "--auth-launch" in content

@patch("PySide6.QtWidgets.QSystemTrayIcon.showMessage")
def test_apply_substitution_permission_error(mock_show_message, tmp_path):
    from locking.launcher_sub import apply_substitution
    
    user_desktop_dir = str(tmp_path / "user_desktop")
    backup_dir = str(tmp_path / "backup")
    system_desktop_dir = str(tmp_path / "system_desktop")
    
    os.makedirs(system_desktop_dir, exist_ok=True)
    sys_file = os.path.join(system_desktop_dir, "test.desktop")
    with open(sys_file, "w") as f:
        f.write("[Desktop Entry]\nExec=kitty\n")
        
    # Force PermissionError when writing the user-level desktop file
    original_open = open
    def mock_open(file, mode="r", *args, **kwargs):
        if mode == "w" and "user_desktop" in str(file):
            raise PermissionError("[Errno 13] Permission denied", file)
        return original_open(file, mode, *args, **kwargs)
        
    with patch("locking.launcher_sub.USER_DESKTOP_DIR", user_desktop_dir), \
         patch("locking.launcher_sub.BACKUP_DIR", backup_dir), \
         patch("locking.launcher_sub.SYSTEM_DESKTOP_DIRS", [system_desktop_dir]), \
         patch("builtins.open", side_effect=mock_open), \
         patch("logging.error") as mock_log_error:
         
         # Create a dummy tray icon so notify_permission_error finds it
         tray = QSystemTrayIcon(app)
         
         apply_substitution([{"desktop_name": "test.desktop"}])
         
         # Assert that logging.error was called with the literal failing path
         failing_path = os.path.join(user_desktop_dir, "test.desktop")
         mock_log_error.assert_called()
         # Check that one of the calls contains the failing path
         logged_path_found = any(failing_path in call_args[0][0] for call_args in mock_log_error.call_args_list)
         assert logged_path_found, "Failing path should be logged"
         
         # Assert tray message was shown
         mock_show_message.assert_called_once()
         title, msg = mock_show_message.call_args[0][:2]
         assert "FaceGate Protection Failed" in title
         assert "test.desktop" in msg
         assert failing_path in msg

def test_get_installed_desktop_entries(tmp_path):
    from utils.desktop_entry_scanner import get_installed_desktop_entries
    
    # Create mock directories
    dir1 = tmp_path / "usr_share"
    dir2 = tmp_path / "usr_local"
    dir3 = tmp_path / "flatpak"
    dir4 = tmp_path / "local_share"
    
    os.makedirs(dir1, exist_ok=True)
    os.makedirs(dir2, exist_ok=True)
    os.makedirs(dir3, exist_ok=True)
    os.makedirs(dir4, exist_ok=True)
    
    # Write mock .desktop files
    with open(dir1 / "app1.desktop", "w") as f:
        f.write("[Desktop Entry]\nName=App One\nExec=app1\nIcon=icon1\n")
    with open(dir2 / "app2.desktop", "w") as f:
        f.write("[Desktop Entry]\nName=App Two\nExec=app2\n")
    with open(dir3 / "app3.desktop", "w") as f:
        f.write("[Desktop Entry]\nName=App Three\nExec=app3\n")
    with open(dir4 / "app4.desktop", "w") as f:
        f.write("[Desktop Entry]\nName=App Four\nExec=app4\n")
        
    apps = get_installed_desktop_entries([str(dir1), str(dir2), str(dir3), str(dir4)])
    
    # Verify all apps are found and sorted alphabetically by name
    assert len(apps) == 4
    assert apps[0]["name"] == "App Four"
    assert apps[1]["name"] == "App One"
    assert apps[2]["name"] == "App Three"
    assert apps[3]["name"] == "App Two"
