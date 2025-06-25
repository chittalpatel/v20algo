#!/bin/bash

# V20Algo OCI Deployment Script
# This script updates an existing V20Algo installation on OCI

set -e

echo "Starting V20Algo deployment on OCI..."

# Configuration
PROJECT_DIR="/home/ubuntu/v20algo"
VENV_PATH="$PROJECT_DIR/venv"
SERVICES=("v20algo-continuous-sync-oci" "v20algo-flask-app-oci")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as ubuntu user
if [ "$USER" != "ubuntu" ]; then
    print_error "This script should be run as ubuntu user"
    exit 1
fi

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Project directory $PROJECT_DIR does not exist"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    print_error "Virtual environment not found at $VENV_PATH"
    exit 1
fi

print_status "Stopping existing services..."
for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        print_status "Stopping $service..."
        sudo systemctl stop "$service"
    else
        print_warning "$service is not running"
    fi
done

# Wait a moment for services to stop
sleep 2

print_status "Pulling latest changes from git..."
cd "$PROJECT_DIR"

# Check if this is a git repository
if [ -d ".git" ]; then
    # Stash any local changes
    if ! git diff-index --quiet HEAD --; then
        print_warning "Local changes detected, stashing them..."
        git stash
    fi

    # Pull latest changes
    print_status "Pulling latest changes..."
    git pull origin main

    # Apply stashed changes if any
    if git stash list | grep -q "stash@{0}"; then
        print_status "Applying stashed changes..."
        git stash pop
    fi
else
    print_warning "Not a git repository, skipping git pull"
fi

print_status "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

print_status "Updating Python dependencies..."
# Upgrade pip first
pip install --upgrade pip

# Install/update requirements
print_status "Installing requirements from requirements.txt..."
pip install -r requirements.txt

print_status "Setting proper permissions..."
chmod +x *.py

print_status "Starting services..."
for service in "${SERVICES[@]}"; do
    print_status "Starting $service..."
    sudo systemctl start "$service"

    # Wait a moment and check if service started successfully
    sleep 3
    if systemctl is-active --quiet "$service"; then
        print_status "$service: ${GREEN}RUNNING${NC}"
    else
        print_error "$service: ${RED}FAILED${NC}"
        print_status "Checking logs for $service..."
        sudo journalctl -u "$service" -n 10
    fi
done

print_status "Deployment completed!"
echo ""
echo "Service Management Commands:"
echo "  Check status: sudo systemctl status v20algo-continuous-sync-oci"
echo "  View logs:    sudo journalctl -u v20algo-continuous-sync-oci -f"
echo "  Restart:      sudo systemctl restart v20algo-continuous-sync-oci"
echo ""
echo "Flask App:"
echo "  Check status: sudo systemctl status v20algo-flask-app-oci"
echo "  View logs:    sudo journalctl -u v20algo-flask-app-oci -f"
echo "  Restart:      sudo systemctl restart v20algo-flask-app-oci"
echo ""
echo "Access your application at: http://$(curl -s ifconfig.me):8000"
