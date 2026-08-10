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
            
            # Verify the PID is in _not_suspicious_pids (stored as (pid, create_time) tuple)
            assert any(k[0] == 99999 for k in monitor._not_suspicious_pids)
            
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


def test_critical_process_denylist_safety_override():
    mock_main_app = MagicMock()
    mock_main_app.is_active.return_value = True
    mock_main_app.get_protected_apps.return_value = [
        {"id": "gnome-shell", "executable": "gnome-shell", "desktop_name": "gnome-shell.desktop"}
    ]
    mock_main_app.is_app_authorized.return_value = False
    mock_main_app.auth_timestamps = {}
    mock_main_app.config = {"security.session_timeout_seconds": 300}

    monitor = AppMonitor(mock_main_app, poll_interval=0.1)

    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 1234,
        "name": "gnome-shell",
        "exe": "/usr/bin/gnome-shell"
    }
    mock_proc.is_running.return_value = True

    with patch("psutil.process_iter", return_value=[mock_proc]), \
         patch("psutil.pids", return_value=[1234]), \
         patch("locking.app_monitor.shutil.which", return_value="/usr/bin/gnome-shell"), \
         patch("locking.app_monitor.calculate_sha256", return_value="matching_hash"), \
         patch("os.stat") as mock_stat:

        mock_stat_res = MagicMock()
        mock_stat_res.st_mtime = 100.0
        mock_stat_res.st_size = 500
        mock_stat.return_value = mock_stat_res

        monitor.running = True
        def mock_sleep(interval):
            monitor.running = False

        with patch("time.sleep", side_effect=mock_sleep), \
             patch("os.kill") as mock_os_kill:
            monitor._monitor_loop()
            # Safety net should override and refuse to suspend gnome-shell
            mock_os_kill.assert_not_called()
            assert any(k[0] == 1234 for k in monitor._not_suspicious_pids)


def test_sha256_hash_collision_ignored_when_name_mismatches():
    mock_main_app = MagicMock()
    mock_main_app.is_active.return_value = True
    mock_main_app.get_protected_apps.return_value = [
        {"id": "my_app", "executable": "my_app", "desktop_name": "my_app.desktop"}
    ]
    mock_main_app.is_app_authorized.return_value = False
    mock_main_app.auth_timestamps = {}
    mock_main_app.config = {"security.session_timeout_seconds": 300}

    monitor = AppMonitor(mock_main_app, poll_interval=0.1)
    # Target hash mapped to my_app
    monitor._hash_map = {"shared_electron_hash": {"id": "my_app", "executable": "my_app", "desktop_name": "my_app.desktop"}}

    # Running process has different executable path & different process name (e.g. electron_app2)
    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 5555,
        "name": "unrelated_launcher",
        "exe": "/opt/unrelated/launcher"
    }
    mock_proc.is_running.return_value = True

    with patch("psutil.process_iter", return_value=[mock_proc]), \
         patch("psutil.pids", return_value=[5555]), \
         patch("locking.app_monitor.shutil.which", return_value="/usr/bin/my_app"), \
         patch("locking.app_monitor.calculate_sha256", return_value="shared_electron_hash"), \
         patch("os.stat") as mock_stat:

        mock_stat_res = MagicMock()
        mock_stat_res.st_mtime = 200.0
        mock_stat_res.st_size = 1000
        mock_stat.return_value = mock_stat_res

        monitor.running = True
        def mock_sleep(interval):
            monitor.running = False

        with patch("time.sleep", side_effect=mock_sleep), \
             patch("os.kill") as mock_os_kill:
            monitor._monitor_loop()
            # Mismatched process name should cause hash match to be ignored as a collision
            mock_os_kill.assert_not_called()
            assert "/opt/unrelated/launcher" in monitor._negative_hash_cache


def test_session_manager_id_normalization():
    from core.session_manager import SessionManager
    mock_config = MagicMock()
    mock_config.get.return_value = True
    protected_apps = [
        {"id": "kitty", "name": "Kitty Terminal", "desktop_name": "kitty.desktop", "executable": "kitty"}
    ]
    sm = SessionManager(config=mock_config, protected_apps_provider=lambda: protected_apps)

    # Test normalization in get_app_id_from_desktop
    assert sm.get_app_id_from_desktop("kitty.desktop") == "kitty"
    assert sm.get_app_id_from_desktop("kitty") == "kitty"

    # Test authorization via desktop name and query via app_id
    sm.authorize_app("kitty.desktop")
    assert sm.is_app_authorized("kitty") is True
    assert sm.is_app_authorized("kitty.desktop") is True
    assert "kitty" in sm.auth_timestamps

    # Test relock via app_id and query via desktop name
    sm.relock_app("kitty")
    assert sm.is_app_authorized("kitty") is False
    assert sm.is_app_authorized("kitty.desktop") is False
    assert "kitty" not in sm.auth_timestamps


def test_app_monitor_authorized_zero_timestamp_does_not_relock():
    mock_main_app = MagicMock()
    mock_main_app.is_active.return_value = True
    mock_main_app.get_protected_apps.return_value = [
        {"id": "kitty", "executable": "kitty", "desktop_name": "kitty.desktop"}
    ]
    mock_main_app.get_app_id_from_desktop.side_effect = lambda x: "kitty"
    mock_main_app.is_app_authorized.return_value = True
    # Simulate missing auth timestamp (0)
    mock_main_app.auth_timestamps = {}
    mock_main_app.config = {"security.session_timeout_seconds": 300}

    monitor = AppMonitor(mock_main_app, poll_interval=0.1)
    monitor._canonical_map = {
        "/usr/bin/kitty": {"id": "kitty", "executable": "kitty", "desktop_name": "kitty.desktop"}
    }

    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 8888,
        "name": "kitty",
        "exe": "/usr/bin/kitty"
    }
    mock_proc.is_running.return_value = True

    with patch("psutil.process_iter", return_value=[mock_proc]), \
         patch("psutil.pids", return_value=[8888]), \
         patch("os.stat") as mock_stat:

        mock_stat_res = MagicMock()
        mock_stat_res.st_mtime = 100.0
        mock_stat_res.st_size = 500
        mock_stat.return_value = mock_stat_res

        monitor.running = True
        def mock_sleep(interval):
            monitor.running = False

        with patch("time.sleep", side_effect=mock_sleep):
            monitor._monitor_loop()

            # Verify relock_app was NOT called
            mock_main_app.relock_app.assert_not_called()
            # Verify PID was added to _seen_pids
            assert any(k[0] == 8888 for k in monitor._seen_pids)
            # Verify auth_timestamp was initialized
            assert mock_main_app.auth_timestamps.get("kitty", 0) > 0


def test_get_process_display_env():
    from core.auth_coordinator import get_process_display_env
    dummy_environ_data = b"DISPLAY=:0\0WAYLAND_DISPLAY=wayland-0\0FOO=BAR\0XAUTHORITY=/home/user/.Xauthority\0"
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=lambda s: MagicMock(read=lambda: dummy_environ_data), __exit__=lambda s, a, b, c: None))):
        env = get_process_display_env(1234)
        assert env.get("DISPLAY") == ":0"
        assert env.get("WAYLAND_DISPLAY") == "wayland-0"
        assert env.get("XAUTHORITY") == "/home/user/.Xauthority"
        assert "FOO" not in env



