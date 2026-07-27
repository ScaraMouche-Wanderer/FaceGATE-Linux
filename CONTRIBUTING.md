# Contributing to FaceGate-Linux

Thank you for your interest in contributing to **FaceGate-Linux**! FaceGate is an open-source, local biometric application security daemon for Linux desktop environments. We welcome all contributions — from bug fixes and documentation improvements to new biometric features and desktop environment integrations!

---

## 🚀 Quick Navigation

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Environment Setup](#development-environment-setup)
- [Codebase Architecture Map](#codebase-architecture-map)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Submitting a Pull Request](#submitting-a-pull-request)

---

## 📜 Code of Conduct

We are committed to providing a welcoming, respectful, and inclusive community for everyone. Please be polite, constructive, and supportive in all issues, pull requests, and discussions.

---

## 🎯 How Can I Contribute?

Here are some great ways to get involved:

### 🌟 Good First Issues (Beginner Friendly)
- **Localization & i18n**: Help translate GUI strings into your native language.
- **Desktop Environment Support**: Test and adapt tray icon behaviors on KDE Plasma, XFCE, Sway, or Hyprland.
- **UI & UX Polish**: Improve visual cues, dark/light theme tokens, or high-DPI scaling policies.
- **Documentation**: Improve setup guides, troubleshooting steps, or security model documentation.

### 🛠️ Advanced Features (Core Engineering)
- **PAM Integration**: Connect FaceGate authentication with Linux Pluggable Authentication Modules (`pam_facegate`).
- **Wayland Protocol Enhancements**: Expand window interception capabilities under pure Wayland compositors (Mutter, KWin, Wayfire).
- **Liveness Checking Upgrades**: Implement 3D depth map heuristics or infrared (IR) camera stream support.
- **Hardware Acceleration**: Add GPU acceleration support via CUDA or DirectML ONNX Runtime providers.

---

## 💻 Development Environment Setup

We use **Poetry** for dependency and environment management.

### 1. Prerequisites
- Python 3.10 or higher
- PySide6 / Qt6 system dependencies (`libxcb`, `libgl`, etc.)
- OpenCV & ONNX Runtime

### 2. Clone & Install
```bash
# 1. Clone the repository
git clone https://github.com/ScaraMouche-Wanderer/FaceGATE-Linux.git
cd FaceGATE-Linux

# 2. Install dependencies via Poetry
poetry install

# 3. Enter the development environment shell
poetry shell
```

---

## 🗺️ Codebase Architecture Map

| Module Directory | Description & Key Responsibilities |
|---|---|
| **`src/core/`** | Application lifecycle, system tray integration, systemd signal handlers, and main loop. |
| **`src/database/`** | RAM-backed tmpfs session key storage (`embedding_store.py`), AES-256-GCM envelope serializer. |
| **`src/security/`** | PBKDF2 key derivation (`crypto_engine.py`), Master Password verification (`credential_store.py`), and intruder selfie logic. |
| **`src/recognition/`** | InsightFace `buffalo_l` ONNX model loading (`detector.py`), cosine similarity matcher (`matcher.py`), and liveness checks (`liveness.py`). |
| **`src/locking/`** | App launch monitor daemon (`AppMonitor`), D-Bus IPC service (`ipc_service.py`), and `.desktop` substitution engine (`launcher_sub.py`). |
| **`src/ui/`** | PySide6 modern user interfaces (`SettingsWindow`, `AuthDialog`, `EnrollmentWizard`, `theme.py`). |
| **`tests/`** | Unit & integration test suite (`pytest`, `unittest.mock`). |

---

## 🧪 Testing & Quality Assurance

Before submitting a Pull Request, ensure that all unit and integration tests pass cleanly:

```bash
# Run the full test suite
poetry run pytest tests/ -v
```

### Writing Tests for New Features
- Place new tests inside the `tests/` directory matching the module name (e.g. `tests/test_feature_name.py`).
- Use `unittest.mock` to mock hardware components (camera feed, D-Bus service, systemd) to ensure tests run headlessly in CI/CD pipelines.

---

## 📥 Submitting a Pull Request

1. **Fork the Repository**: Create your own fork of `FaceGATE-Linux`.
2. **Create a Feature Branch**:
   ```bash
   git checkout -b feature/amazing-new-feature
   ```
3. **Commit Your Changes**: Use clear, descriptive commit messages.
   ```bash
   git commit -m "feat(ui): add high-contrast dark theme palette and custom combo box delegate"
   ```
4. **Push & Open PR**: Push to your branch and open a Pull Request targeting `master`!

We review all pull requests promptly and provide friendly, constructive feedback. Thank you for making Linux desktop security better for everyone! 🚀
