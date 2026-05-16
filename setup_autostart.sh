#!/bin/bash

# Ensure the script is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo (e.g., sudo ./setup_autostart.sh)"
  exit 1
fi

# We need the real user who ran sudo, not root, so we can recover their graphical session
if [ -z "$SUDO_USER" ]; then
  echo "This script must be run via sudo, not directly as root."
  exit 1
fi

SUDO_UID_VAL=$(id -u "$SUDO_USER")
PROJECT_DIR="$(pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Python virtual environment not found at $VENV_PYTHON"
    echo "Please set up the virtual environment first."
    exit 1
fi

SERVICE_FILE="/etc/systemd/system/codemaker.service"

echo "Creating systemd service at $SERVICE_FILE..."

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=CodeMaker — AI code ghost-typing service
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=root
Environment=SUDO_USER=$SUDO_USER
Environment=SUDO_UID=$SUDO_UID_VAL
Environment=HOME=/home/$SUDO_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PYTHON -m codemaker
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOF

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling CodeMaker to start on boot..."
systemctl enable codemaker

echo "Starting CodeMaker service..."
systemctl restart codemaker

echo ""
echo "✅ Autostart setup complete!"
echo "CodeMaker is now running in the background and will start automatically on boot."
echo "Logs are being written to both journalctl and $PROJECT_DIR/codemaker.log"
echo ""
echo "To view status:  sudo systemctl status codemaker"
echo "To view logs:    tail -f codemaker.log"
echo "To stop:         sudo systemctl stop codemaker"
