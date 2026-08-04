# FaceGATE-Linux User & Developer Guide 🛡️👤

Welcome to the definitive user and developer guide for **FaceGATE-Linux**, a high-performance local biometric security daemon and application lock framework for Linux desktop environments.

This guide provides exhaustive instructions for using FaceGATE via the terminal, configuring system settings, integrating FaceGATE across desktop environments and workflows, running the test suite with `pytest`, and understanding every command and security feature.

---

## 📋 Table of Contents

1. [System Architecture & Overview](#1-system-architecture--overview)
2. [Terminal Usage & Command-Line Reference](#2-terminal-usage--command-line-reference)
3. [Installation & Systemd Daemon Management](#3-installation--systemd-daemon-management)
4. [Settings & Configuration Reference](#4-settings--configuration-reference)
5. [Implementation Scenarios & Integration Points](#5-implementation-scenarios--integration-points)
6. [Testing Guide: Running Pytest & Benchmarks](#6-testing-guide-running-pytest--benchmarks)
7. [Emergency Recovery & Troubleshooting](#7-emergency-recovery--troubleshooting)

---

## 1. System Architecture & Overview

FaceGATE-Linux operates as an unprivileged background daemon (`systemd --user`) paired with a Qt6 system tray interface and local machine-learning biometric pipeline.

### Core Protection Layers

1. **Launcher Shadowing (Primary Layer)**:
   - Substitutes desktop application launchers (`.desktop` files in `~/.local/share/applications/`) with lightweight wrappers.
   - When an application icon is clicked, the wrapper communicates with the running daemon over Session D-Bus (`org.facegate.FaceGate`) to require facial or password authentication before spawning the binary.

2. **Process Monitor & Interception (Backstop Layer)**:
   - An asynchronous scanning thread (`AppMonitor`) polls active processes using `psutil`.
   - If a protected application process starts directly (e.g., from terminal or a custom script bypassing `.desktop` files), `AppMonitor` immediately sends a `SIGSTOP` signal to suspend the process execution, opening the biometric authentication dialog before sending `SIGCONT` (or `SIGKILL` on auth failure/timeout).

3. **Local Machine-Learning Biometrics**:
   - Uses ONNX Runtime and the lightweight `buffalo_l` InsightFace model for **100% offline, local facial recognition**.
   - **Anti-Spoofing / Liveness Check**: Evaluates bounding-box centroid micro-motion across confirmation frames to reject static photographs or digital screen spoofs.

4. **Cryptographic Security & Session Vault**:
   - Master Passwords use PBKDF2-HMAC-SHA256 derivation with **600,000 iterations**.
   - Facial embeddings and audit data are encrypted at rest with AES-256-GCM.
   - Encryption keys are cached in user-private RAM `tmpfs` (`/run/user/{uid}/facegate.key`) to ensure keys are zeroed upon session logout or system shutdown.
   - Core dumps are explicitly disabled (`PR_SET_DUMPABLE = 0`) to prevent key leakage.

---

## 2. Terminal Usage & Command-Line Reference

The main entry point for terminal interaction is the `facegate` binary (installed to `~/.local/bin/facegate` or executed via `poetry run facegate`).

### CLI Command Options

| Command / Flag | Description | Example Usage |
| :--- | :--- | :--- |
| `--monitor` | Starts the background lock daemon, D-Bus service, process scanner, and system tray icon. | `facegate --monitor` |
| `--settings` | Launches the graphical Settings Dashboard (requires Admin face verification or Master Password). | `facegate --settings` |
| `--enroll <username>` | Enrolls facial biometric profile for `<username>` via CLI capture wizard. | `facegate --enroll admin` |
| `--set-master-password` | Sets or updates the Master Password interactively. | `facegate --set-master-password` |
| `--enable` | Enables and resumes FaceGATE monitoring via D-Bus or starts systemd user service. | `facegate --enable` |
| `--disable [MINUTES]` | Temporarily pauses FaceGATE monitoring for `N` minutes (default: 15 mins). Restores launchers while paused. | `facegate --disable 30` |
| `--lock-all` | Sends a instant **Panic Lockdown** signal to the daemon, re-locking all protected apps immediately. | `facegate --lock-all` |
| `--emergency-kill` | Sends an emergency termination signal to the running daemon via D-Bus. | `facegate --emergency-kill` |
| `--restore-launchers` | Emergency recovery: restores all modified `.desktop` launchers to original backup state. | `facegate --restore-launchers` |
| `--restore-all` | Emergency recovery: restores desktop launchers and clears runtime lock state. | `facegate --restore-all` |
| `--recognize <app_id>` | Internal/Subprocess: Launches isolated recognition dialog for a specific target app. | `facegate --recognize google-chrome` |
| `--auth-launch <app_id> -- <cmd>` | Launcher wrapper mode: checks D-Bus authentication before executing target command. | `facegate --auth-launch kitty -- kitty` |

---

## 3. Installation & Systemd Daemon Management

### 1. Automated Installation
Clone the repository and run the installer script:
```bash
git clone https://github.com/ScaraMouche-Wanderer/FaceGATE-Linux.git
cd FaceGATE-Linux
./install.sh
```

The installer will:
1. Initialize the Python virtual environment via Poetry (`poetry install`).
2. Symlink the `facegate` executable to `~/.local/bin/facegate`.
3. Register the systemd user service unit (`~/.config/systemd/user/facegate.service`).
4. Reload the `systemd --user` manager daemon.

### 2. Managing the Systemd User Service

You can control FaceGATE like any Linux system service:

- **Start Daemon**:
  ```bash
  systemctl --user start facegate.service
  ```
- **Enable Daemon on System Startup / Login**:
  ```bash
  systemctl --user enable facegate.service
  ```
- **Check Service Status**:
  ```bash
  systemctl --user status facegate.service
  ```
- **Stop Daemon**:
  ```bash
  systemctl --user stop facegate.service
  ```
- **View Live Logs**:
  ```bash
  journalctl --user -u facegate.service -f
  ```

### 3. Uninstallation & Launcher Restoration
To safely remove FaceGATE and restore all original desktop application launchers:
```bash
./install.sh --uninstall
```

---

## 4. Settings & Configuration Reference

FaceGATE loads configuration from `config/default.yaml` and user overrides in `~/.config/facegate/default.yaml`. Hot-reloading allows settings to update live without restarting the daemon.

### Configuration Schema (`default.yaml`)

```yaml
app_monitor:
  poll_interval_seconds: 0.2     # Frequency of process scanning (lower = faster detection window)
  on_auth_failure: kill         # Action on auth failure/cancel ('kill' process or keep suspended)
  auth_timeout_seconds: 60      # Auth dialog window auto-timeout limit in seconds

protected_apps:                 # List of protected applications
  - id: google-chrome
    name: Google Chrome
    desktop_name: google-chrome.desktop
    binary_path: /usr/bin/google-chrome

authentication:
  password_fallback_grace_seconds: 15 # Seconds before Master Password button is shown

recognition:
  similarity_threshold: 0.52     # Minimum Cosine similarity score (0.0 to 1.0) for match
  ambiguity_margin: 0.03        # Safety score margin required between top two user matches
  liveness_min_motion: 0.5      # Minimum bounding-box centroid movement (px) to prevent photo spoofing

security:
  session_timeout_seconds: 300  # Inactivity duration before authorized session auto-locks
  pbkdf2_iterations: 600000     # PBKDF2 iteration count for Master Password key derivation
  salt_length_bytes: 16         # Cryptographic salt size in bytes
  lock_settings_window: true    # Require Admin biometric/password verification to open Settings

behavior:
  launcher_recheck_interval_minutes: 10 # Periodic timer to verify launcher shadowing integrity
  notify_on_auth: true                  # Show desktop notification on app lock/unlock
  autolock_on_idle: false               # Enable autolock when user desktop is idle
  autolock_on_idle_minutes: 10          # Desktop idle duration threshold
  startup_delay_seconds: 0              # Startup delay for slow desktop environments
  launch_at_login: true                 # Launch daemon on desktop login
  uninstall_protection: true            # Prompt for auth before quitting/uninstalling
  lock_on_sleep_or_lock: true           # Re-lock all apps on system suspend or screensaver lock
  theme: light                          # Base UI theme ('light' or 'dark')
  color_palette: iron_ember             # Preset palette ('iron_ember', 'violet_slate', 'amber_espresso', 'emerald_obsidian')
  tray_icon_style: circle               # System tray icon glyph ('circle', 'square', 'shield', 'lock', 'gate')

camera:
  backend: V4L2                         # OpenCV camera backend
  fps: 30                               # Target frame rate
  width: 640                            # Video frame width
  height: 480                           # Video frame height
  skip_frames: 2                        # Frame skip factor for low CPU consumption
  ir_color_variance_threshold: 15.0     # Infrared camera variance filter

database:
  path: ~/.config/facegate/facegate.db  # SQLite database location

ui:
  developer_mode: false                 # Enable developer debug metrics
  fps_counter: true                     # Show camera FPS overlay in auth dialog
  logging_enabled: true                 # Enable UI file logging
```

---

## 5. Implementation Scenarios & Integration Points

FaceGATE-Linux can be implemented across various Linux desktop environments, window managers, and security workflows:

### 1. Desktop Environments & Window Managers
- **GNOME / KDE Plasma / XFCE / Cinnamon / MATE**:
  - Full system tray integration (`FaceGateTray`).
  - Supports standard `.desktop` launcher substitution (`/usr/share/applications/` -> `~/.local/share/applications/`).
  - Integrated D-Bus listeners for GNOME ScreenSaver (`org.gnome.ScreenSaver`), KDE ScreenSaver (`org.freedesktop.ScreenSaver`), and Xfce ScreenSaver (`org.xfce.ScreenSaver`).
- **Tiling Window Managers (Sway, Hyprland, i3, bspwm, Wayfire)**:
  - Supports Wayland (`WAYLAND_DISPLAY`) and X11 (`DISPLAY`).
  - Hotkey bindings can be configured in window manager config files (e.g., `hyprland.conf` or `sway/config`):
    ```ini
    # Example Hyprland Panic Hotkey binding
    bind = SUPER_SHIFT, L, exec, facegate --lock-all
    ```

### 2. Common Application Protection Use Cases
- **Web Browsers (Chrome, Firefox, Brave, Vivaldi)**: Protect stored cookies, active sessions, and saved credentials.
- **Terminal Emulators (Kitty, Alacritty, GNOME Terminal)**: Protect active root shell sessions, SSH agent keys, and server infrastructure access.
- **Password Managers & Wallets (KeePassXC, Bitwarden, Crypto Wallets)**: Provide an instant biometric gate before opening password vaults.
- **System Tools & File Managers (GParted, Dolphin, Nautilus)**: Prevent unauthorized system configuration changes or browsing of private directories.

### 3. Custom CLI & Script Integration
You can gate any custom executable or script behind FaceGATE biometric authentication by using `--auth-launch`:
```bash
# Wrap a custom sensitive script:
facegate --auth-launch custom_script -- /path/to/my_sensitive_script.sh
```

---

## 6. Testing Guide: Running Pytest & Benchmarks

FaceGATE includes a comprehensive test suite powered by `pytest` and `pytest-qt` covering cryptographic security, face matching, liveness verification, process interception, and launcher substitution.

### 1. Running the Full Test Suite
To run all automated unit and integration tests:
```bash
poetry run pytest tests/ -v
```

### 2. Running Specific Test Modules

| Test Module | Component Tested | Command |
| :--- | :--- | :--- |
| **`test_security.py`** | Security auditing, brute-force lockout policies, session timeout, core dump protection. | `poetry run pytest tests/test_security.py -v` |
| **`test_crypto_engine.py`** | PBKDF2 key derivation, AES-256-GCM encryption, RAM key vault caching. | `poetry run pytest tests/test_crypto_engine.py -v` |
| **`test_liveness.py`** | Centroid micro-motion anti-spoof checks and motion threshold validation. | `poetry run pytest tests/test_liveness.py -v` |
| **`test_app_monitor.py`** | `AppMonitor` process scanning loop, process matching, and `SIGSTOP` suspension. | `poetry run pytest tests/test_app_monitor.py -v` |
| **`test_ui_recognition.py`** | PySide6 AuthDialog UI, camera worker lifecycle, and password fallback. | `poetry run pytest tests/test_ui_recognition.py -v` |
| **`test_auth_queue.py`** | Serialized request queueing, concurrency guards, and memory leak prevention. | `poetry run pytest tests/test_auth_queue.py -v` |
| **`test_matcher.py`** | Cosine similarity embedding matrix scoring and threshold verification. | `poetry run pytest tests/test_matcher.py -v` |
| **`test_launcher_manager.py`** | Launcher substitution manager, backup integrity, and system recovery. | `poetry run pytest tests/test_launcher_manager.py -v` |
| **`test_launcher_sub.py`** | `.desktop` wrapper file generation and command parsing. | `poetry run pytest tests/test_launcher_sub.py -v` |
| **`test_backstop_latency.py`** | Latency benchmarks for process interception windows. | `poetry run pytest tests/test_backstop_latency.py -v` |
| **`test_recognition_smoke.py`** | Smoke test for InsightFace detector and embedding extractor initialization. | `poetry run pytest tests/test_recognition_smoke.py -v` |

### 3. Useful Pytest Execution Flags
- **Filter by keyword**:
  ```bash
  poetry run pytest -k "liveness" -v
  ```
- **Show stdout logging during test run**:
  ```bash
  poetry run pytest tests/ -s
  ```
- **Stop on first failure**:
  ```bash
  poetry run pytest tests/ -x
  ```
- **Show slowest test executions**:
  ```bash
  poetry run pytest tests/ --durations=5
  ```

### 4. Running Performance & FPS Benchmarks
To measure real-time camera processing performance, frame rates, and model inference latency on your hardware:
```bash
poetry run python tests/benchmark_fps.py
```

---

## 7. Emergency Recovery & Troubleshooting

### Emergency Launcher Restoration
If system crashes occur or desktop launchers remain substituted while the daemon is inactive, run the emergency restore command:
```bash
facegate --restore-all
```
This instantly reverts all modified `.desktop` files in `~/.local/share/applications/` back to their original binary paths.

### Built-in Keyboard Shortcuts
- **Panic Lockdown**: `<Control><Alt>l` (Instantly re-locks all protected applications).
- **Emergency Recovery**: `<Control><Alt>k` (Triggers launcher restoration).

### Checking Log Files
- **Daemon Systemd Journal**: `journalctl --user -u facegate.service -f`
- **Local Application Log**: `cat ~/.config/facegate/facegate.log`

---

*FaceGATE-Linux is licensed under the MIT License. Developed by ScaraMouche-Wanderer.*
