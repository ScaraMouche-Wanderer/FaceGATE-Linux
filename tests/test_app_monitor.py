import os
import time
import pytest
from unittest.mock import patch, MagicMock
from locking.app_monitor import AppMonitor

def test_app_monitor_negative_cache():
    # Mock main_app and its config/methods
    mock_main_app = MagicMock()
    mock_main_app.is_active.return_value = True
    mock_main_app.get_protected_apps.return_value = [
        {"id": "kitty", "executable": "kitty", "desktop_name": "kitty.desktop"}
    ]
    mock_main_app.is_app_authorized.return_value = False
    mock_main_app.auth_timestamps = {}
    mock_main_app.config = {
        "security.session_timeout_seconds": 300
    }
    
    # Instantiate AppMonitor
    monitor = AppMonitor(mock_main_app, poll_interval=0.1)
    
    # Prepare dummy heuristics so matching proceeds to hash checks
    dummy_app_cfg = {"id": "kitty", "executable": "kitty", "desktop_name": "kitty.desktop"}
    monitor._heuristics = [("kitty", dummy_app_cfg, "dummy_target_hash")]
    
    # We simulate a running process whose name matches the heuristic (contains "kitty")
    # but whose actual file hash does not match.
    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 99999,
        "name": "not_really_kitty_but_has_kitty_substring",
        "exe": "/usr/bin/not_kitty"
    }
    mock_proc.is_running.return_value = True
    
    # Mock psutil.process_iter to return our suspicious process
    def mock_calc_hash_func(path):
        if "not_kitty" in path:
            return "different_hash"
        return "dummy_target_hash"

    with patch("psutil.process_iter", return_value=[mock_proc]), \
         patch("psutil.pids", return_value=[99999]), \
         patch("locking.app_monitor.shutil.which", return_value="/usr/bin/kitty"), \
         patch("locking.app_monitor.calculate_sha256", side_effect=mock_calc_hash_func) as mock_calc_hash, \
         patch("os.stat") as mock_stat:
         
        # Set up stat output
        mock_stat_res = MagicMock()
        mock_stat_res.st_mtime = 123456789.0
        mock_stat_res.st_size = 98765
        mock_stat.return_value = mock_stat_res
        
        # Run first loop iteration
        monitor.running = True
        def mock_sleep(interval):
            monitor.running = False
            
        with patch("time.sleep", side_effect=mock_sleep):
            monitor._monitor_loop()
            
            # Verify calculate_sha256 was called twice (once for cache init, once for suspicious process scan)
            assert mock_calc_hash.call_count == 2
            
            # Verify the PID is in _not_suspicious_pids
            assert 99999 in monitor._not_suspicious_pids
            
            # Verify the executable is in the negative cache
            assert "/usr/bin/not_kitty" in monitor._negative_hash_cache
            
            # Clear non-suspicious set to force re-evaluation of same executable under a new/reused PID
            monitor._not_suspicious_pids.clear()
            monitor._seen_pids.clear()
            
            # Run second loop iteration
            monitor.running = True
            with patch("time.sleep", side_effect=mock_sleep):
                monitor._monitor_loop()
                
            # Assert calculate_sha256 was NOT called a third time (remains 2)
            assert mock_calc_hash.call_count == 2
