# Changelog

All notable changes to the FaceGate-Linux project will be documented in this file.

---

## [v0.7.0] - 2026-07-10 (Current Phase)
### Added
- **Intruder Selfie Capture**: Automatically snaps and saves a webcam photo of unauthorized access attempts locally on authentication cancellation, failure, or timeout.
- **Intruder Gallery Tab**: A premium visual dashboard in the Settings window to view and delete captured intruder selfies.
- **Path-Aliasing Prevention**: Added canonical absolute path checking for process monitoring, mitigating symlink and dot-relative bypasses.
- **Copy-Bypass Heuristics**: Added conditional SHA-256 hash checks on suspicious process binaries to block physical copies of locked executables.

### Fixed
- **UI Responsiveness & DPI Scaling**: Refactored Settings, Wizard, and Auth dialogs to scale size dynamically based on screen resolution and DPI.
- **Keyboard Usability**: Wired the "Enter" and "Return" keys as default triggers across all wizard stages and password fallback input boxes.

---

## [v0.6.0]
### Added
- **Guided Setup Wizard**: Introduced a step-by-step GUI wizard for enrollment, helping users align their face and calibrate templates.

---

## [v0.5.0]
### Added
- **Audit Logs**: SQLite logging system for authorization attempts (timestamp, action, outcome, and method).

---

## [v0.4.0]
### Added
- **Liveness Checking**: Real-time blink and head-pose challenge verification to prevent static photo or video bypasses.

---

## [v0.3.0]
### Added
- **AES-256-GCM Encryption**: Secure PBKDF2-HMAC-SHA256 (600k iterations) key derivation to encrypt facial templates and configs at rest.

---

## [v0.2.0]
### Added
- **InsightFace Recognition**: Integrated ONNX Runtime face detection and comparison in a lightweight short-lived subprocess.

---

## [v0.1.0]
### Added
- **Daemon Core**: Background process monitor using `psutil`, `SIGSTOP` suspensions, D-Bus IPC service, systemd user service packaging, and desktop application launcher shadowing overrides.
