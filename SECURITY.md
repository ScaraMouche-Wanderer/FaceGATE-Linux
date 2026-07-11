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

## Cryptographic Details

- **Encryption**: AES-256-GCM (via Python `cryptography` library)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP 2024 recommendation)
- **Salt**: 16 bytes, cryptographically random (`os.urandom`)
- **Nonce**: 12 bytes (96-bit), fresh per encryption operation
