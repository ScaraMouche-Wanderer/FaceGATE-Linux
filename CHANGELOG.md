# Changelog

All notable changes to the FaceGate-Linux project will be documented in this file.

---

## [v1.2.0] - 2026-08-20
### Added
- **Presence Sentry (Walk-Away Proximity Auto-Lock)**: Periodic lightweight presence sentinel that automatically re-locks active sessions if the user leaves their workstation.
- **Emergency Duress Password & Silent Panic Alarm**: Covert protection under coercion that immediately triggers a panic lockdown, takes an intruder webcam snapshot, and logs a tamper-evident audit record.
- **Glassmorphism Biometric HUD**: Ultra-minimal floating capsule overlay at top-center of the screen providing non-intrusive status confirmations on app unlock/lock.
- **Quick CLI App Management**: Added `--quick-add <app>`, `--remove <app>`, `--lock <app>`, and `--set-duress-password` for fast terminal control.
- **Multi-Factor Biometric Liveness & Anti-Spoofing Engine**: Integrated landmark-derived Eye Aspect Ratio (EAR) blink analysis, 3D head pose estimation (yaw, pitch, roll angles), and multi-signal fusion against presentation attacks.
- **Granular Per-App Security Policies**: Added support for individual `session_timeout_seconds` and custom `auth_mode` ("face", "password", "face+password" 2FA) overrides per protected application.
- **Hardware Camera Diagnostics & Lighting Quality Engine**: Added Linux V4L2 device capability inspection (`query_v4l2_capabilities`), device diagnostics (`get_camera_details`), and real-time ambient lighting assessment (`calculate_frame_lighting`).
- **Cryptographic Audit Trail Export & Maintenance**: Added one-click CSV and JSON audit log exporting (`--export-logs`), signed genesis audit log clearing, and instant cryptographic hash chain integrity verification (`--verify-integrity`).
- **New Theme Presets**: Added "Nordic Frost (Deep Navy & Ice Blue)" and "Synthwave (Obsidian & Vivid Magenta)" palettes for both dark and light modes.
- **CLI Benchmark & Profile Utilities**: Added `--benchmark`, `--list-profiles`, and `--delete-profile` for rapid terminal management.


---

## [v0.7.0] - 2026-07-10

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
