import pytest
from unittest.mock import patch, MagicMock

from utils.hotkey_manager import (
    get_current_custom_bindings,
    register_gnome_hotkey,
    unregister_gnome_hotkey,
    register_lock_hotkey,
    unregister_lock_hotkey,
    CUSTOM_PATH,
    LOCK_PATH
)

@patch("utils.hotkey_manager.subprocess.run")
def test_get_current_custom_bindings(mock_run):
    mock_run.return_value.stdout = "['/path/one/', '/path/two/']\n"
    bindings = get_current_custom_bindings()
    assert bindings == ['/path/one/', '/path/two/']

@patch("locking.launcher_sub.get_facegate_executable", return_value="/usr/bin/facegate")
@patch("utils.hotkey_manager.get_current_custom_bindings", return_value=[])
@patch("utils.hotkey_manager.subprocess.run")
def test_register_gnome_hotkey(mock_run, mock_bindings, mock_exe):
    res = register_gnome_hotkey("<Control><Alt>k")
    assert res is True
    assert mock_run.call_count >= 2

@patch("utils.hotkey_manager.get_current_custom_bindings", return_value=[CUSTOM_PATH])
@patch("utils.hotkey_manager.subprocess.run")
def test_unregister_gnome_hotkey(mock_run, mock_bindings):
    res = unregister_gnome_hotkey()
    assert res is True
    mock_run.assert_called_once()
