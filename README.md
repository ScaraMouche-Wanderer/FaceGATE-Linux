# FaceGate-Linux

FaceGate-Linux is a locking skeleton tray daemon and app monitor built using PySide6 and D-Bus.

## Installation & Setup

Ensure you have Poetry installed:
```bash
poetry install
```

## Running the Application

To run the monitor daemon:
```bash
poetry run facegate --monitor
```

---

## How this works, and its limits

### 1. Polling vs. Event-Based Process Scanning
We utilize `psutil` polling to scan for protected app processes at a configured interval (`app_monitor.poll_interval_seconds`, default `1.5` seconds).
- **Trade-off**: This introduces a latency window bounded by the poll interval (empirically measured average detection delay: **1.0462 seconds**). 
- **Alternative**: Netlink process connector (`CONFIG_PROC_EVENTS`) would offer event-driven, near-zero latency scanning but requires kernel-level netlink socket access and `CAP_NET_ADMIN` privilege grants. We avoided this to ensure FaceGate runs cleanly as a personal, unprivileged desktop user application.

### 2. SIGSTOP Process Interception
On process launch detection, we issue a `SIGSTOP` signal to suspend the application process rather than immediately executing `SIGKILL`.
- **Reasoning**: This preserves the process's internal execution state. If the user successfully authenticates, we send `SIGCONT` to resume execution without work loss. `SIGKILL` is only executed if authentication fails or the dialog times out.

### 3. Flatpak Integration Limitation
Desktop launcher shadowing works by overriding `.desktop` files in the user-level directory `~/.local/share/applications/`. Flatpak runtimes can regenerate their exported desktop files upon app updates, which silently reverts launcher substitutions.
- **Mitigation**: We re-apply and verify launcher substitutions on every daemon startup. Note that this mitigation is not airtight if an update occurs mid-session.

### 4. What the initial version does not do
- **No Face Recognition**: The authentication gate is a temporary, plaintext password-only dialog (`admin` by default). Liveness detection and model inference are implemented in biometric releases.
- **No Encrypted Credential Storage**: Password verification is a plaintext-in-memory-only placeholder. PBKDF2-tuned validation and AES-256-GCM encrypted-at-rest key rings are deferred to security updates.
- **No systemd Packaging**: Automatic daemon startup is not handled in this release.

---

## Face Recognition & Subprocess Architecture

Face recognition introduces real face recognition using **InsightFace** (`buffalo_l` model) and **ONNX Runtime**.

### 1. Short-Lived Subprocess Model
To maintain a low idle memory footprint, the main resident daemon process (`facegate --monitor`) does not import any computer vision or machine learning libraries (such as `cv2`, `numpy`, `insightface`, or `onnxruntime`). 

Instead, when an authentication challenge is triggered, the daemon spawns a short-lived subprocess (`facegate --recognize <desktop_name>`). This subprocess:
1. Loads the `buffalo_l` face recognition models (average load time: **0.8057 seconds**).
2. Spawns a dedicated camera thread running at **30 FPS** and `640x480` resolution.
3. Captures, detects, and validates faces against enrolled user templates.
4. Exits with a predefined exit code contract.

### 2. Exit Code Contract
The `--recognize` subprocess communicates authentication results to the parent daemon using exit codes:
- `0`: **Authenticated**: Face matched successfully.
- `1`: **Rejected**: Face matching finished, but similarity was below threshold or ambiguous.
- `2`: **Timeout**: Authentication timed out before a face could be matched.
- `3`: **Camera/Model Error**: Failed to open the camera device or initialize models.
- `4`: **Password Fallback**: User chose to authenticate using a password instead.

If the subprocess exits with `3` (error) or `4` (password fallback), the parent daemon falls back to showing the password dialog in-process, ensuring the user is never locked out.

### 3. Wayland Camera Permissions
Under standard Arch Linux GNOME Wayland desktop environments, native desktop applications are not prompted for camera permissions. Unsandboxed applications can directly access `/dev/video*` devices, provided the running user is a member of the Unix `video` group.

### 4. CLI Enrollment
To enroll a face template:
```bash
poetry run facegate --enroll <username>
```
This utility captures sharp, non-blurry frames, extracts the embeddings, averages them to create a template, and immediately discards all raw images from memory.

