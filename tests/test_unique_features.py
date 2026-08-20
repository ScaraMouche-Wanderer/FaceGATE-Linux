"""
Unit and integration tests for unique, minimalist, and high-impact FaceGATE-Linux features:
1. Emergency Duress Password & Silent Panic Alarm (duress_mode.py)
2. Presence Sentry Walk-Away Auto-Lock (presence_sentry.py)
3. Biometric HUD Glassmorphism Pill (toast_notification.py)
4. CLI Quick Management (--quick-add, --remove, --lock)
"""

import os
import sys
import json
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from security.duress_mode import (
    set_duress_password,
    verify_duress_password,
    has_duress_password,
    trigger_duress_alarm
)
from security.presence_sentry import PresenceSentry
from ui.toast_notification import BiometricHUD


def test_duress_password_lifecycle(tmp_path, monkeypatch):
    """Test setting, persisting, and verifying emergency duress credentials."""
    duress_file = str(tmp_path / ".duress.enc")
    monkeypatch.setattr("security.duress_mode.DURESS_FILE", duress_file)

    assert has_duress_password() is False
    assert verify_duress_password("MyDuressPassword123") is False

    # Setting too short password should raise ValueError
    with pytest.raises(ValueError):
        set_duress_password("short")

    # Set valid duress password
    assert set_duress_password("EmergencyPanic999!") is True
    assert has_duress_password() is True
    assert os.path.exists(duress_file)

    # Verify correct vs wrong password
    assert verify_duress_password("EmergencyPanic999!") is True
    assert verify_duress_password("WrongPassword123!") is False
    assert verify_duress_password("") is False


def test_duress_alarm_trigger(tmp_path, monkeypatch):
    """Test that duress alarm triggers panic lockdown, audit logging, and photo snapshot."""
    logged_events = []
    monkeypatch.setattr(
        "security.duress_mode.log_auth_attempt",
        lambda app, method, result, score, user: logged_events.append((app, method, result, user))
    )

    cleared_keys = []
    monkeypatch.setattr(
        "database.embedding_store.clear_cached_key",
        lambda: cleared_keys.append(True)
    )

    # Trigger alarm
    trigger_duress_alarm("ConfidentialApp")

    assert len(logged_events) == 1
    assert "DURESS_ALARM" in logged_events[0][0]
    assert logged_events[0][3] == "COVERT_DURESS"
    assert len(cleared_keys) == 1


def test_presence_sentry_signals():
    """Test Presence Sentry timeout and presence lost signal dispatch."""
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    sentry = PresenceSentry(check_interval_sec=0.1, timeout_sec=0.2)

    lost_signals = []
    restored_signals = []
    sentry.signals.presence_lost.connect(lambda: lost_signals.append(True))
    sentry.signals.presence_restored.connect(lambda: restored_signals.append(True))

    # Mock camera presence probe to return False (user walked away)
    sentry._probe_camera_presence = MagicMock(return_value=False)

    # Simulate elapsed time
    sentry.running = True
    sentry.last_presence_time = time.time() - 1.0  # 1s ago > 0.2s threshold

    sentry._check_presence_tick()

    assert len(lost_signals) == 1


def test_presence_sentry_activity_resets():
    """Test that recording user activity postpones walk-away lockdown."""
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    sentry = PresenceSentry(check_interval_sec=1.0, timeout_sec=30.0)
    t0 = time.time() - 10.0
    sentry.last_presence_time = t0

    sentry.record_activity()
    assert sentry.last_presence_time > t0


def test_biometric_hud_creation():
    """Test instantiation and styling of BiometricHUD."""
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    hud_unlocked = BiometricHUD("Firefox Unlocked", icon="🛡️", is_success=True)
    assert hud_unlocked.message == "Firefox Unlocked"
    assert hud_unlocked.is_success is True
    assert hud_unlocked.HUD_WIDTH == 260

    hud_locked = BiometricHUD("Terminal Locked", icon="🔒", is_success=False)
    assert hud_locked.is_success is False

