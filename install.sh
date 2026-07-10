#!/bin/bash
set -e

echo "=== FaceGate-Linux Installer ==="

# 1. Verify Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "Error: Poetry is not installed."
    echo "Please install Poetry first (e.g. via pipx or your system package manager) before running this script."
    exit 1
fi

echo "Poetry found at $(which poetry)."

# 2. Run poetry install
echo "Setting up virtual environment and installing dependencies..."
poetry install

# 3. Determine the real path of the poetry wrapper script
VENV_PATH=$(poetry env info --path)
VENV_FACEGATE="$VENV_PATH/bin/facegate"

if [ ! -f "$VENV_FACEGATE" ]; then
    echo "Error: Poetry environment script not found at $VENV_FACEGATE."
    exit 1
fi

echo "Resolved Poetry wrapper script: $VENV_FACEGATE"

# Symlink to ~/.local/bin/facegate
mkdir -p "$HOME/.local/bin"
echo "Creating symlink ~/.local/bin/facegate -> $VENV_FACEGATE"
ln -sf "$VENV_FACEGATE" "$HOME/.local/bin/facegate"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "⚠️  WARNING: $HOME/.local/bin is not in your current PATH."
    echo "Please add it to your PATH in your shell configuration (e.g., ~/.bashrc, ~/.zshrc or ~/.profile):"
    echo '    export PATH="$HOME/.local/bin:$PATH"'
    echo ""
fi

# 4. Copy systemd user service unit
echo "Registering systemd user service..."
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

# Copy packaging/facegate.service replacing ExecStart path if needed
# We use %h in systemd which is systemd's specifier for user's home directory.
cp packaging/facegate.service "$SYSTEMD_USER_DIR/facegate.service"

# 5. Reload systemd daemon manager
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo ""
echo "=========================================================="
echo "SUCCESS: FaceGate-Linux has been successfully installed!"
echo "=========================================================="
echo "To start the daemon now, run:"
echo "    systemctl --user start facegate.service"
echo ""
echo "To check daemon logs/status, run:"
echo "    systemctl --user status facegate.service"
echo "    journalctl --user -u facegate.service -f"
echo ""
echo "To enable FaceGate to run automatically on system login:"
echo "    systemctl --user enable facegate.service"
echo "=========================================================="
echo ""
