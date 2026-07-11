# Contributing to FaceGate-Linux

Thank you for your interest in contributing to FaceGate-Linux! To maintain a clean and reliable codebase, please follow the guidelines below.

---

## Development Environment Setup

We use **Poetry** for dependency and environment management.

1. Install Poetry if you haven't already:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```
2. Clone the repository and install dependencies (including development tools):
   ```bash
   poetry install
   ```
3. Run the development shell:
   ```bash
   poetry shell
   ```

---

## Testing & Quality Control

Before submitting any code changes, ensure all unit and integration tests pass successfully:

```bash
poetry run pytest
```

Ensure new features are accompanied by corresponding unit or smoke tests under the `tests/` directory.

### Code Style Guidelines
- Write readable, PEP-8 compliant Python.
- Retain detailed comments and logging outputs (particularly for security-sensitive IPC, D-Bus, and process management routines).
- Use Qt layout managers and dynamic size/scaling policies for all PySide6 UI elements to ensure high-DPI and multi-resolution compatibility.

