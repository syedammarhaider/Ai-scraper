#!/bin/bash

# ======================================================
# Deployment script for AI Scraper - Uses Systemd ONLY
# ======================================================
set -e  # Exit on any error

echo "🚀 Starting deployment..."

# -----------------------------
# Project directory
# -----------------------------
PROJECT_DIR=/home/ec2-user/Ai-scraper
PYTHON=python3
PIP=pip3

# -----------------------------
# Stop any running instances first
# -----------------------------
echo "🛑 Stopping existing services..."
sudo systemctl stop ai-scraper 2>/dev/null || true

# Kill any remaining processes on port 8000
sleep 2
sudo fuser -k 8000/tcp 2>/dev/null || true

# Kill any orphan uvicorn processes
pkill -f "uvicorn.*app" 2>/dev/null || true
sleep 2

# -----------------------------
# Go to project directory
# -----------------------------
cd $PROJECT_DIR || {
    echo "❌ Cannot change to project directory ($PROJECT_DIR)"
    exit 1
}

# -----------------------------
# Pull latest changes
# -----------------------------
echo "📥 Pulling latest changes..."
git fetch origin main
git reset --hard origin/main
git pull origin main

# -----------------------------
# Install dependencies
# -----------------------------
echo "📦 Installing dependencies..."
$PIP install --user -r requirements.txt 2>/dev/null || {
    echo "⚠️ Using pip3 install..."
    pip3 install --user -r requirements.txt
}

# -----------------------------
# Verify installation
# -----------------------------
echo "🔍 Checking installation..."
$PYTHON -c "import fastapi, uvicorn; print('✅ Dependencies OK')"

# -----------------------------
# Ensure systemd service uses correct module path
# -----------------------------
echo "🔧 Updating systemd service if needed..."
SERVICE_FILE="/etc/systemd/system/ai-scraper.service"

if [ -f "$SERVICE_FILE" ]; then
    # Fix the ExecStart line if it has old path
    sudo sed -i 's/app\.app:app/app:app/g' $SERVICE_FILE
    echo "✅ Systemd service updated"
    
    # Reload systemd
    sudo systemctl daemon-reload
fi

# -----------------------------
# Start the application via systemd
# -----------------------------
echo "🔥 Starting application via systemd..."
sudo systemctl start ai-scraper

# -----------------------------
# Wait for startup
# -----------------------------
echo "⏳ Waiting for application to start..."
sleep 5

# -----------------------------
# Check status
# -----------------------------
if sudo systemctl is-active --quiet ai-scraper; then
    echo "✅ Application is running successfully"
    echo "🌐 Server should be available at: http://YOUR_SERVER_IP/"
    
    # Health check
    echo "🔍 Performing health check..."
    sleep 2
    if curl -f -s --max-time 10 http://localhost:8000/health > /dev/null; then
        echo "✅ Health check passed"
        echo "🎉 Deployment completed successfully!"
        exit 0
    else
        echo "⚠️ Service running but health endpoint not responding yet"
        echo "📋 Service status:"
        sudo systemctl status ai-scraper -l --no-pager || true
        exit 0
    fi
else
    echo "❌ Application failed to start"
    echo "📋 Service status:"
    sudo systemctl status ai-scraper -l --no-pager || true
    echo "📋 Recent logs:"
    sudo journalctl -u ai-scraper -n 20 --no-pager || true
    exit 1
fi

