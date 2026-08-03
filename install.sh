#!/bin/bash
set -e

echo "=== FaceGate-Linux Installer ==="

# Handle uninstall flag
if [ "$1" == "--uninstall" ]; then
    echo "Uninstalling FaceGate-Linux..."
    if command -v facegate &> /dev/null; then
        facegate --restore-launchers || true
    elif [ -f "$HOME/.local/bin/facegate" ]; then
        "$HOME/.local/bin/facegate" --restore-launchers || true
    fi
    echo "Stopping and disabling systemd service..."
    systemctl --user stop facegate.service || true
    systemctl --user disable facegate.service || true
    rm -f "$HOME/.config/systemd/user/facegate.service"
    systemctl --user daemon-reload || true
    rm -f "$HOME/.local/bin/facegate"
    echo "FaceGate-Linux successfully uninstalled and all launchers restored!"
    exit 0
fi

if [ "$1" == "--restore-launchers" ]; then
    if [ -f "$HOME/.local/bin/facegate" ]; then
        "$HOME/.local/bin/facegate" --restore-launchers
    else
        echo "Error: facegate command not found in ~/.local/bin/facegate"
        exit 1
    fi
    exit 0
fi
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
