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
