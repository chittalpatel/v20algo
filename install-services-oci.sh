#!/bin/bash

# V20Algo OCI Service Installation Script
# This script installs systemd services for the V20Algo application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== V20Algo OCI Service Installation ===${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Check if virtual environment exists
if [[ ! -d "/home/ubuntu/v20algo/venv" ]]; then
    echo -e "${RED}Error: Virtual environment not found at /home/ubuntu/v20algo/venv${NC}"
    echo -e "${YELLOW}Please create the virtual environment first:${NC}"
    echo "cd /home/ubuntu/v20algo"
    echo "python3 -m venv venv"
    echo "source venv/bin/activate"
    echo "pip install -r requirements.txt"
    exit 1
fi

# Check if service files exist
if [[ ! -f "v20algo-continuous-sync-oci.service" ]] || [[ ! -f "v20algo-flask-app-oci.service" ]]; then
    echo -e "${RED}Error: Service files not found in current directory${NC}"
    exit 1
fi

echo -e "${YELLOW}Installing systemd services...${NC}"

# Copy service files to systemd directory
cp v20algo-continuous-sync-oci.service /etc/systemd/system/
cp v20algo-flask-app-oci.service /etc/systemd/system/

# Set proper permissions
chmod 644 /etc/systemd/system/v20algo-*.service

# Reload systemd daemon
systemctl daemon-reload

echo -e "${GREEN}Services installed successfully!${NC}"

# Enable services
echo -e "${YELLOW}Enabling services...${NC}"
systemctl enable v20algo-continuous-sync-oci.service
systemctl enable v20algo-flask-app-oci.service

echo -e "${GREEN}Services enabled successfully!${NC}"

echo -e "${YELLOW}Service Status:${NC}"
echo "Continuous Sync Service: $(systemctl is-enabled v20algo-continuous-sync-oci.service)"
echo "Flask App Service: $(systemctl is-enabled v20algo-flask-app-oci.service)"

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${YELLOW}To start the services, run:${NC}"
echo "sudo systemctl start v20algo-continuous-sync-oci.service"
echo "sudo systemctl start v20algo-flask-app-oci.service"
echo ""
echo -e "${YELLOW}To check service status:${NC}"
echo "sudo systemctl status v20algo-continuous-sync-oci.service"
echo "sudo systemctl status v20algo-flask-app-oci.service"
