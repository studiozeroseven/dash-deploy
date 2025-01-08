#!/bin/bash

# Installer for Dash Deployment CLI
# Automates the setup and installation process on an Ubuntu server.

# Update and install system dependencies
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "Installing required system packages..."
sudo apt install -y python3-pip python3-venv git

# Clone the repository
echo "Cloning the Dash Deployment CLI repository..."
git clone https://github.com/yourusername/dash-deployment-cli.git
cd dash-deployment-cli

# Create a virtual environment
echo "Creating a Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Make the installer executable
echo "Making the installer executable..."
chmod +x installer.sh

# Run the Dash Deployment CLI installer
echo "Starting the Dash Deployment CLI"
python3 dash_deploy.py
