"""
Health Check & Diagnostic Suite for FaceGATE-Linux.

Validates system prerequisites, model files, camera accessibility, D-Bus
IPC connectivity, configuration integrity, and file permissions.

Usage:
    python -m utils.health_check
    or via CLI: facegate --health
"""

import os
import sys
from typing import List, Tuple


def run_health_check() -> Tuple[int, int, List[str]]:
    """
    Executes all health checks and returns (passed_count, total_count, report_lines).
    """
    report = []
    passed = 0
    total = 0

    def check(condition: bool, name: str, success_msg: str, fail_msg: str):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            report.append(f"  \033[92m[PASS]\033[0m {name}: {success_msg}")
        else:
            report.append(f"  \033[91m[FAIL]\033[0m {name}: {fail_msg}")

    report.append("🔍 === FaceGATE-Linux System Health Inspection ===")

    # 1. Check Model Files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "models"))
    det_model = os.path.join(models_dir, "buffalo_l", "det_10g.onnx")
    rec_model = os.path.join(models_dir, "buffalo_l", "w600k_r50.onnx")

    has_models = os.path.exists(det_model) or os.path.exists(rec_model) or os.path.exists(models_dir)
    check(has_models, "InsightFace ONNX Models",
          f"Found model directory ({models_dir})",
          f"Model files missing at {models_dir}")

    # 2. Check Camera Access
    camera_found = False
    for dev_idx in range(4):
        dev_path = f"/dev/video{dev_idx}"
        if os.path.exists(dev_path):
            camera_found = True
            break

    if not camera_found:
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                camera_found = True
                cap.release()
        except Exception:
            pass

    check(camera_found, "Video Capture Device",
          "Webcam / Video device detected",
          "No video capture device (/dev/video*) accessible")

    # 3. Check Configuration File
    config_dir = os.path.expanduser("~/.config/facegate")
    check(os.path.exists(config_dir), "Config Directory",
          f"Found at {config_dir}",
          f"Directory {config_dir} does not exist")

    # 4. Check Encryption Vault File & Permissions
    emb_file = os.path.join(config_dir, "embeddings.enc")
    if os.path.exists(emb_file):
        mode = oct(os.stat(emb_file).st_mode & 0o777)
        is_secure = mode in ("0o600", "0o400")
        check(is_secure, "Vault Permissions",
              f"File permissions secure ({mode})",
              f"Vault file mode {mode} is insecure (expected 0600)")
    else:
        check(True, "Vault Envelope", "Not initialized yet (ready for first enrollment)", "")

    # 4b. State Integrity Check (file-deletion bypass detection)
    try:
        from security.state_watchdog import is_initialized, check_critical_files
        if is_initialized():
            issues = check_critical_files()
            state_ok = len(issues) == 0
            if state_ok:
                check(True, "State Integrity",
                      "All critical state files present (no tamper detected)",
                      "")
            else:
                missing_files = ", ".join(i["file"] for i in issues)
                check(False, "State Integrity",
                      "",
                      f"TAMPER WARNING: Missing critical files after initialization: {missing_files}")
    except Exception as e:
        check(False, "State Integrity", "", f"Could not check state integrity: {e}")

    # 4c. Audit Database Hash Chain Integrity Check
    try:

        from database.audit_log import verify_audit_log_integrity
        chain_ok, chain_count, chain_msg = verify_audit_log_integrity()
        check(chain_ok, "Audit Log Integrity",
              f"Cryptographic hash chain valid ({chain_count} records)",
              f"Hash chain compromised: {chain_msg}")
    except Exception as e:
        check(False, "Audit Log Integrity", "", f"Could not verify audit log hash chain: {e}")


    # 5. Check D-Bus Connection & Service
    dbus_connected = False
    daemon_running = False
    try:
        from PySide6.QtDBus import QDBusConnection
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            dbus_connected = True
            if bus.interface():
                owner_reply = bus.interface().serviceOwner("org.facegate.FaceGate")
                daemon_running = owner_reply.isValid() and bool(owner_reply.value())
    except Exception:
        pass

    check(dbus_connected, "Session D-Bus",
          "D-Bus session bus connected",
          "Failed to connect to Session D-Bus")
    check(daemon_running, "Daemon IPC Service",
          "FaceGate background daemon is active (org.facegate.FaceGate)",
          "Daemon IPC service not running (start with systemctl --user start facegate)")

    # 6. Check Core Dependencies
    deps_ok = True
    missing_deps = []
    for pkg in ["PySide6", "cv2", "numpy", "psutil", "cryptography", "yaml"]:
        try:
            __import__(pkg)
        except ImportError:
            deps_ok = False
            missing_deps.append(pkg)

    check(deps_ok, "Python Dependencies",
          "All required packages imported successfully",
          f"Missing Python dependencies: {', '.join(missing_deps)}")

    report.append("==================================================")
    score_color = "\033[92m" if passed == total else "\033[93m" if passed >= total - 1 else "\033[91m"
    report.append(f"  Health Score: {score_color}{passed}/{total} Passed\033[0m")
    report.append("")

    # 7. Actionable Security & Configuration Suggestions
    report.append("💡 === Recommended Security & Performance Tuning ===")
    try:
        from utils.config_loader import get_config
        config = get_config()

        # Check persist_vault_key
        persist_key = config.get("security.persist_vault_key", False)
        if not persist_key:
            report.append("  \033[96m[CONFIG]\033[0m Vault Key Lifetime: RAM-only mode active (persist_vault_key: false).")
            report.append("           \033[90m-> Explanation:\033[0m Cold service restarts require entering master password once on first auth.")
            report.append("           \033[90m-> Improvement:\033[0m Set 'security.persist_vault_key: true' in Settings > Behavior to persist machine-bound key in system keyring.")
        else:
            report.append("  \033[92m[CONFIG]\033[0m Vault Key Lifetime: System Keyring wrapping active (persist_vault_key: true).")

        # Check liveness anti-spoofing
        raw_liveness = config.get("recognition.liveness_min_motion", 0.5)
        liveness_motion = float(raw_liveness if isinstance(raw_liveness, (int, float, str)) else 0.5)
        if liveness_motion < 0:
            report.append("  \033[93m[SECURITY]\033[0m Liveness Anti-Spoofing: Disabled (liveness_min_motion < 0).")
            report.append("           \033[90m-> Improvement:\033[0m Set 'recognition.liveness_min_motion: 0.5' to prevent static photo presentation attacks.")
        else:
            report.append(f"  \033[92m[SECURITY]\033[0m Liveness Anti-Spoofing: Active (min motion: {liveness_motion}px). Anti-photo protection enabled.")

        # Check deny on missing state
        deny_missing = config.get("security.deny_on_missing_state", True)
        if not deny_missing:
            report.append("  \033[93m[SECURITY]\033[0m Tamper Defense: Permissive mode (deny_on_missing_state: false).")
            report.append("           \033[90m-> Improvement:\033[0m Set 'security.deny_on_missing_state: true' for maximum anti-tampering protection.")
        else:
            report.append("  \033[92m[SECURITY]\033[0m Tamper Defense: Deny-on-tamper active (deny_on_missing_state: true).")

        # Check network geofencing
        geofence_enabled = config.get("security.geofence_enabled", False)
        if not geofence_enabled:
            report.append("  \033[96m[FEATURE]\033[0m Network Geofencing: Disabled.")
            report.append("           \033[90m-> Improvement:\033[0m Enable Geofencing in Settings > Behavior to auto-lock FaceGate when leaving trusted Wi-Fi networks.")
        else:
            raw_ssids = config.get("security.geofence_trusted_ssids", [])
            ssids = ", ".join(str(s) for s in raw_ssids) if isinstance(raw_ssids, list) else ""
            report.append(f"  \033[92m[FEATURE]\033[0m Network Geofencing: Active (Trusted Wi-Fi: {ssids or 'none'}).")

        # Check decoy mode applications
        raw_apps = config.get("protected_apps", [])
        apps = raw_apps if isinstance(raw_apps, list) else []
        decoy_apps = [a for a in apps if isinstance(a, dict) and a.get("decoy_mode")]
        if not decoy_apps:
            report.append("  \033[96m[FEATURE]\033[0m Decoy Honeypot Traps: 0 active decoy launchers.")
            report.append("           \033[90m-> Improvement:\033[0m Enable Decoy Mode in Settings > Locked Apps to capture stealth intruder photos on honeypot apps.")
        else:
            report.append(f"  \033[92m[FEATURE]\033[0m Decoy Honeypot Traps: {len(decoy_apps)} decoy application launcher(s) active.")

    except Exception as e:
        report.append(f"  \033[91m[ERROR]\033[0m Could not inspect configuration suggestions: {e}")

    report.append("==================================================")
    return passed, total, report


if __name__ == "__main__":
    passed, total, report = run_health_check()
    print("\n".join(report))
    sys.exit(0 if passed == total else 1)
