# FaceGATE Linux — project brief

A Linux desktop application locker that brings local face recognition, an encrypted profile vault, authentication coordination, and process monitoring into one native interface.

**Stack:** Python · PySide6/Qt · OpenCV · InsightFace · ONNX Runtime · SQLite · systemd user services

## Start here

- [User and developer guide](GUIDE.md): installation, configuration, and workflow.
- [Security model](SECURITY.md): enforcement boundary and known limitations.
- [Authentication coordinator](src/core/auth_coordinator.py): authentication flow.
- [Process monitor](src/locking/app_monitor.py): application detection.
- [Tests](tests/): recognition, locking, crypto, and UI behavior.

## Implementation map

| Layer | Source | Responsibility |
| :--- | :--- | :--- |
| Camera acquisition | [camera_worker.py](src/camera/camera_worker.py) | Camera frames for recognition |
| Recognition | [detector.py](src/recognition/detector.py), [matcher.py](src/recognition/matcher.py), [liveness.py](src/recognition/liveness.py) | Face detection, matching, and motion checks |
| Coordination | [auth_coordinator.py](src/core/auth_coordinator.py) | Coordinate requests and authentication outcomes |
| Enforcement | [launcher_sub.py](src/locking/launcher_sub.py), [app_monitor.py](src/locking/app_monitor.py) | Launcher substitution and process-monitor backstop |
| Profile security | [crypto_engine.py](src/security/crypto_engine.py), [credential_store.py](src/security/credential_store.py) | Encrypted profile data and credentials |
| Desktop interface | [auth_dialog.py](src/ui/auth_dialog.py), [settings_window.py](src/ui/settings_window.py) | Authentication and application configuration |

## Design decisions worth discussing

- **Keep recognition local.** ONNX inference avoids sending camera frames to a cloud recognition service, at the cost of model installation and local compute.
- **Coordinate a stateful workflow.** Camera access, dialogs, process suspension, cancellation, and credential fallback must agree on the authentication result.
- **Use layered application interception.** Desktop launcher substitution covers a common launch path; polling provides a backstop for direct process launches.
- **Document the threat model.** A user-level daemon cannot enforce a security boundary against root. Polling introduces an exposure window, and motion-only liveness can be vulnerable to dynamic presentation attacks.

## Three-minute demonstration

1. Show the protected-application list and local settings.
2. Open the documented enrollment/authentication flow using a consenting local test profile.
3. Explain the password fallback and encrypted profile storage.
4. Show one process-monitor or crypto regression, then the matching limitation in [SECURITY.md](SECURITY.md).

The [recorded interface demo](assets/demo.gif) is available for a review without camera access.

## Reproduce checks

Follow the dependency setup in [GUIDE.md](GUIDE.md), then:

```bash
poetry run pytest tests/ -v
```

Some tests and workflows depend on GUI, camera, or model availability. Use the [actual workflow runs](../../actions) for current CI status; a demo image is not evidence of a passing test suite.

## Scope

This is a personal desktop privacy tool with explicit limitations. It does not replace OS login, PAM, kernel access control, or hardware-backed biometric authentication. AES-GCM protects stored profile data; it does not remove the enforcement limitations of a user-level application locker.
