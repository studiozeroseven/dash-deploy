#!/bin/bash

# Bootstrap installer for the Dash Deployment CLI (Ubuntu).
# Installs system deps, creates a venv, then launches the CLI.

set -euo pipefail
cd "$(dirname "$0")"

if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    echo "warning: this tool assumes an Ubuntu server; continuing anyway" >&2
fi

echo "Installing system packages (python3-venv, git)..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install python3-venv git

echo "Creating the CLI virtual environment..."
python3 -m venv .venv
. .venv/bin/activate

echo "Installing the CLI's own dependencies (textual)..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Starting the Dash Deployment CLI (dry-run first is a good idea)..."
echo "  real run:      .venv/bin/python dash_deploy.py"
echo "  dry run:       .venv/bin/python dash_deploy.py --dry-run"
.venv/bin/python dash_deploy.py
