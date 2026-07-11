# Security Policy

## Supported Versions

| Version | Supported              |
| ------- | ---------------------- |
| 0.1.x   | ✅ Currently supported |

## Reporting a Vulnerability

If you discover a security vulnerability in FaceGATE-Linux, **please do not file a public GitHub issue.**

Instead, please report it privately:

1. **Email**: Send a detailed report to the project maintainer ([prathmeshnarwaria@gmail.com]).
2. **GitHub Security Advisories**: Use [GitHub's private vulnerability reporting](https://github.com/ScaraMouche-Wanderer/FaceGATE-Linux/security/advisories/new) to submit a confidential advisory.

### What to Include

- A clear description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact assessment
- Any suggested fixes (optional)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Fix Release**: Within 30 days for critical issues

## Security Model & Known Limitations

FaceGATE-Linux is a **user-level** application locker. It is designed to protect against casual, opportunistic, or physical-presence bypass attempts. It is **not** designed to defend against:

- **Root-level attackers**: Any user with superuser access can trivially bypass FaceGate.
- **Kernel-level attacks**: Debugging via `ptrace`, `/proc/PID/mem`, etc.
- **Physical hardware attacks**: Hardware keyloggers, cold boot attacks, etc.

For a full discussion of the security model, see the [README](README.md#security-model--limitations).

### Process Detection & Interception Model (Direct-Launch Gap)

- **Mechanism**: FaceGATE-Linux enforces locking via a dual-layer approach:
  1. **Launcher Substitution**: It shadows the application's desktop entry (`.desktop` file) to run a helper wrapper that authenticates before executing the binary.
  2. **Process Polling Monitor**: A background monitor (`AppMonitor`) polls running system processes at a configurable interval (default `0.4s`) to detect and suspend (via `SIGSTOP`) unauthorized instances of protected apps.
- **Direct-Launch Exposure**: Because process monitoring relies on a polling thread, there is a sub-second window of exposure between a process spawning and it being detected and suspended.
- **Direct Binary Launch Bypass**: Processes launched directly via their absolute or relative binary paths (e.g. from a terminal, a custom script, or an IDE run configuration) completely bypass the launcher substitution hook. In these cases, protection relies solely on the background process monitor, meaning the application will launch and briefly execute for up to the duration of the polling interval before being suspended and gated by the authentication dialog.

### Liveness Verification (Anti-Spoofing)

FaceGATE-Linux includes a basic motion-based liveness check to prevent static photo or screen bypasses:
- **Mechanism**: Bounding box centroid tracking across the 3 confirmation frames requires a minimum micro-motion threshold (configurable via `recognition.liveness_min_motion` in `default.yaml`).
- **Limitations**: This is a pure motion/jitter check. It does **not** perform hardware-backed 3D depth sensing or active infrared (IR) scanning. Therefore, a high-resolution video of the owner or a dynamic presentation attack could potentially bypass this check.

## Cryptographic Details

- **Encryption**: AES-256-GCM (via Python `cryptography` library)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP 2024 recommendation)
- **Salt**: 16 bytes, cryptographically random (`os.urandom`)
- **Nonce**: 12 bytes (96-bit), fresh per encryption operation
