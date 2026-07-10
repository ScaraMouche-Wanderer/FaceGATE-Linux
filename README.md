# FaceGate-Linux

FaceGate-Linux is a secure, user-level application locker daemon and tray interface for Linux desktop environments. Designed to prevent unauthorized access to sensitive application windows (such as web browsers, terminal consoles, or system settings), FaceGate intercepts target launches and gates them behind fast, local biometric face recognition (powered by InsightFace) and liveness checking, with a secure password fallback.

---

## Features

- **Biometric Application Locking**: Automatically detects process launches and suspends them via `SIGSTOP` until the user is authenticated via face recognition or password.
- **Local Face Recognition**: Employs ONNX Runtime and the lightweight `buffalo_l` InsightFace model to perform real-time, low-latency, private local biometric verification.
- **Biometric Security Hardening**: Built-in blink detection and head-pose liveness checks protect against photo and video spoofing bypass attempts.
- **Intruder Selfie Gallery**: Automatically captures webcam photos of unauthorized users during failed or cancelled authentication attempts and organizes them in a private visual settings gallery.
- **AES-256-GCM Encryption-at-Rest**: Facial embeddings and configuration profiles are encrypted locally using PBKDF2-HMAC-SHA256 (600,000 iterations).
- **Uninstall & Deletion Protection**: Prevents unauthorized modifications, directory deletion, or settings purging by gating configuration changes behind admin verification.
- **Emergency Override**: Configurable GNOME-wide emergency shortcut to stop the daemon and restore processes in case of camera failure.
- **SQLite Audit Trail**: Maintains a local, tamper-evident log of all access attempts, failures, and bypasses, visible via the Settings GUI.
- **Guided GUI Wizard**: Includes an interactive step-by-step setup utility for profile enrollment and system calibration.

---

## Security Model & Limitations

FaceGate-Linux is designed to raise the bar against casual, opportunistic, or physical-presence bypass attempts on shared or unlocked desktop environments. However, users should understand its security model and inherent boundaries:

### 1. The Root Shell Limitation
FaceGate-Linux runs as an unprivileged, user-level daemon (`systemd --user`). This means any user or process with **root (superuser) shell access** can easily bypass the lock. They can kill the daemon, unmount/delete configuration directories (bypassing uninstall protection), modify launcher paths, or read configuration values. FaceGate is intended to protect your personal user session from other local users or casual intruders with physical access to your device — not to defend against a local root administrator.

### 2. Process Detection & Binary Resolution
To detect launched processes, FaceGate polls the system processes list via `psutil` at a configured polling interval (default: `1.5` seconds). This introduces a small, empirical delay (average ~1s) between application launch and window suspension.
- **Symlinks & Path Aliases**: Target applications are matched using their resolved canonical paths (`os.path.realpath(exe)`), preventing trivial path-aliasing bypasses (e.g. running via `/usr/bin/../bin/firefox` or using symlinks).
- **Renamed Copies**: If a user makes a physical copy of a protected binary under a different name (e.g., `cp /usr/bin/firefox /usr/bin/firefox2`), FaceGate employs a name-based heuristic. If the candidate name matches or contains a substring of a protected executable, FaceGate hashes the running binary and compares it with the target binary's cached SHA-256 hash.
- **Dissimilar Copies (Open Gap)**: If an attacker copies a protected binary to an entirely arbitrary, unrelated path and name (e.g., `cp /usr/bin/firefox /tmp/x`), FaceGate's heuristic will not trigger a hash check to avoid CPU regressions. This remains a known limitation of user-level polling.

---

## Installation & Setup

1. Make sure you have Poetry and PySide6 dependencies installed on your system.
2. Clone the repository and run the installation script:
   ```bash
   ./install.sh
   ```
3. The installer compiles assets, configures user systemd services, and registers desktop file overrides.

---

## Screenshots & Visuals

*Screenshots and UI walk-through recordings will be added for the upcoming public release.*
- **Settings Dashboard**: Management of protected applications, liveness settings, and general preferences.
- **Authentication Dialog**: Smooth 30 FPS camera scanner pane with liveness guidance.
- **Intruder Alerts Pane**: Local visual gallery storing attempts and captured webcam feeds.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
