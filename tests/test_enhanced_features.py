"""
Comprehensive unit and integration tests for new and enhanced FaceGATE-Linux features:
1. Biometric EAR calculation & 3D Head Pose estimation
2. Multi-factor liveness assessment
3. Camera device details and capability inspection
4. Per-app session timeouts & policies
5. Audit log CSV/JSON exports and hash chain integrity
6. Theme palettes & color derivation
7. CLI diagnostic command execution
"""

import os
import json
import csv
import numpy as np
from unittest.mock import MagicMock

from recognition.liveness import (
    calculate_eye_aspect_ratio,
    estimate_head_pose,
    evaluate_multi_factor_liveness
)
from recognition.matcher import get_all_match_scores
from camera.camera_worker import calculate_frame_lighting
from database.audit_log import (
    log_auth_attempt,
    verify_audit_log_integrity,
    export_audit_logs
)
from core.session_manager import SessionManager
from ui.theme import get_colors, PALETTES


def test_eye_aspect_ratio_calculation():
    """Verify EAR calculation on known synthetic 5-point facial landmarks."""
    # Empty / invalid landmarks
    assert calculate_eye_aspect_ratio(None) == 0.0
    assert calculate_eye_aspect_ratio([]) == 0.0

    # Normal synthetic 5 keypoints: [left_eye, right_eye, nose, left_mouth, right_mouth]
    # left_eye=(100, 100), right_eye=(200, 100), nose=(150, 150), left_mouth=(120, 200), right_mouth=(180, 200)
    kps = np.array([
        [100.0, 100.0],
        [200.0, 100.0],
        [150.0, 150.0],
        [120.0, 200.0],
        [180.0, 200.0]
    ], dtype=np.float32)

    ear = calculate_eye_aspect_ratio(kps)
    assert ear > 0.5 and ear < 1.5


def test_head_pose_estimation():
    """Verify 3D head pose estimation (yaw, pitch, roll) from 5 keypoints."""
    # Straight forward facing
    kps_front = np.array([
        [100.0, 100.0],
        [200.0, 100.0],
        [150.0, 150.0],
        [120.0, 200.0],
        [180.0, 200.0]
    ], dtype=np.float32)

    yaw, pitch, roll = estimate_head_pose(kps_front)
    assert abs(roll) < 1.0  # Level horizontal eyes
    assert abs(yaw) < 2.0   # Centered nose
    assert abs(pitch) < 5.0

    # Turned right (nose shifted towards right eye at x=180)
    kps_right = np.array([
        [100.0, 100.0],
        [200.0, 100.0],
        [180.0, 150.0],
        [120.0, 200.0],
        [180.0, 200.0]
    ], dtype=np.float32)
    yaw_r, _, _ = estimate_head_pose(kps_right)
    assert yaw_r > 15.0

    # Tilted head (right eye lower than left eye)
    kps_tilted = np.array([
        [100.0, 100.0],
        [200.0, 140.0],
        [150.0, 170.0],
        [120.0, 220.0],
        [180.0, 240.0]
    ], dtype=np.float32)
    _, _, roll_t = estimate_head_pose(kps_tilted)
    assert roll_t > 15.0


def test_multi_factor_liveness_evaluation():
    """Verify multi-factor liveness assessment fusing texture, motion, and pose."""
    # Synthetic frame and moving centroid history
    crop = np.full((100, 100, 3), 128, dtype=np.uint8)
    centroids = [(100.0, 100.0), (103.0, 102.0), (107.0, 105.0)]
    kps_history = [
        np.array([[100, 100], [200, 100], [150, 150], [120, 200], [180, 200]]),
        np.array([[102, 101], [202, 101], [152, 151], [122, 201], [182, 201]])
    ]

    res = evaluate_multi_factor_liveness(crop, centroids, kps_history, min_motion=0.5, allow_synthetic=True)
    assert res["passed"] is True
    assert res["motion_passed"] is True
    assert res["cumulative_motion_px"] > 5.0


def test_get_all_match_scores():
    """Verify matching scores across multiple enrolled users."""
    enrolled = {
        "alice": np.ones(512, dtype=np.float32),
        "bob": np.zeros(512, dtype=np.float32)
    }
    enrolled["bob"][0] = 1.0  # Bob's vector has 1 in first dim

    query = np.ones(512, dtype=np.float32)
    scores = get_all_match_scores(query, enrolled)
    assert len(scores) == 2
    assert scores[0][0] == "alice"
    assert scores[0][1] > 0.99


def test_camera_lighting_metrics():
    """Verify ambient lighting sufficiency calculation."""
    # Dark frame
    dark = np.zeros((100, 100, 3), dtype=np.uint8)
    score_d, status_d = calculate_frame_lighting(dark)
    assert score_d == 0.0
    assert "Dark" in status_d

    # Optimal frame
    mid = np.full((100, 100, 3), 128, dtype=np.uint8)
    score_m, status_m = calculate_frame_lighting(mid)
    assert 40.0 < score_m < 60.0
    assert "Optimal" in status_m


def test_per_app_session_timeouts():
    """Verify that SessionManager respects custom per-app timeout configurations."""
    config = MagicMock()
    config.get.side_effect = lambda k, d=None: 300 if k == "security.session_timeout_seconds" else d

    protected_apps = [
        {
            "id": "org.gnome.Terminal",
            "name": "Terminal",
            "desktop_name": "org.gnome.Terminal.desktop",
            "session_timeout_seconds": 60
        },
        {
            "id": "org.mozilla.firefox",
            "name": "Firefox",
            "desktop_name": "firefox.desktop"
        }
    ]

    sm = SessionManager(config, protected_apps_provider=lambda: protected_apps)

    # Terminal has custom 60s timeout
    assert sm.get_app_session_timeout("org.gnome.Terminal") == 60
    assert sm.get_app_session_timeout("org.gnome.Terminal.desktop") == 60

    # Firefox falls back to global 300s timeout
    assert sm.get_app_session_timeout("org.mozilla.firefox") == 300
    assert sm.get_app_session_timeout("firefox.desktop") == 300


def test_audit_log_export_csv_and_json(tmp_path):
    """Verify CSV and JSON export functions for the audit log database."""
    # Log sample entries
    log_auth_attempt("test_export_app_1", "face", "success", 0.95, "admin")
    log_auth_attempt("test_export_app_2", "password", "fail", 0.0, "unknown")

    # Verify integrity
    is_valid, count, msg = verify_audit_log_integrity()
    assert is_valid is True

    # Export to CSV
    csv_file = str(tmp_path / "audit_test.csv")
    ok_csv, count_csv, _ = export_audit_logs(csv_file, format="csv")
    assert ok_csv is True
    assert count_csv >= 2
    assert os.path.exists(csv_file)

    with open(csv_file, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert "AppIdentifier" in header
        rows = list(reader)
        assert len(rows) >= 2

    # Export to JSON
    json_file = str(tmp_path / "audit_test.json")
    ok_json, count_json, _ = export_audit_logs(json_file, format="json")
    assert ok_json is True
    assert os.path.exists(json_file)

    with open(json_file, "r") as f:
        data = json.load(f)
        assert "records" in data
        assert len(data["records"]) >= 2


def test_theme_palettes_loaded():
    """Verify all theme palettes including Nordic Frost and Synthwave are valid."""
    assert "nordic_frost" in PALETTES
    assert "synthwave_magenta" in PALETTES
    assert "iron_ember" in PALETTES

    c_nordic_dark = get_colors("dark", "nordic_frost")
    assert c_nordic_dark["IS_DARK"] is True
    assert "ACCENT_PURPLE" in c_nordic_dark

    c_synth_light = get_colors("light", "synthwave_magenta")
    assert c_synth_light["IS_DARK"] is False
    assert "BG_NEUTRAL" in c_synth_light
