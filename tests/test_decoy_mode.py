import os
import numpy as np
from unittest.mock import patch, MagicMock

from security.decoy_mode import is_decoy_app, handle_decoy_trigger

def test_is_decoy_app():
    protected_apps = [
        {"id": "firefox", "desktop_name": "firefox.desktop", "is_decoy": False},
        {"id": "secret-vault", "desktop_name": "secret-vault.desktop", "is_decoy": True}
    ]
    
    assert is_decoy_app("firefox", protected_apps) is False
    assert is_decoy_app("secret-vault", protected_apps) is True
    assert is_decoy_app("nonexistent", protected_apps) is False

@patch("security.decoy_mode.QMessageBox")
@patch("security.decoy_mode.log_auth_attempt")
def test_handle_decoy_trigger(mock_log, mock_msgbox, tmp_path):
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    intruder_dir = str(tmp_path / "intruders")
    
    with patch("os.path.expanduser", return_value=intruder_dir):
        mock_msg_instance = MagicMock()
        mock_msgbox.return_value = mock_msg_instance

        handle_decoy_trigger("secret-app", frame=dummy_frame)
        
        # Verify audit log recorded decoy trap failure
        mock_log.assert_called_once_with(
            "secret-app", "decoy_trap", "fail", confidence_score=0.0, username="intruder_trap"
        )
        
        # Verify message box displayed fake crash dialog
        mock_msg_instance.exec.assert_called_once()
        
        # Verify intruder selfie was saved
        assert os.path.exists(intruder_dir)
        files = os.listdir(intruder_dir)
        assert len(files) == 1
        assert files[0].startswith("DECOY_")
