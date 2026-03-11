#!/bin/bash

# ======================================================
# Robust deployment script for hAI Scraper
# ======================================================
set -e  # Exit on any error

echo "🚀 Starting deployment..."

# -----------------------------
# Set Python & Pip explicitly
# -----------------------------
PYTHON=python3
PIP=pip3

# -----------------------------
# Project directory
# -----------------------------
PROJECT_DIR=/home/ec2-user/Ai-scraper

# -----------------------------
# Function to check if process is running
# -----------------------------
check_process() {
    if pgrep -f "$1" > /dev/null; then
        echo "❌ Process $1 is running, killing..."
        pkill -f "$1" || true
        sleep 2
    fi
}

# -----------------------------
# Kill existing processes
# -----------------------------
check_process "uvicorn app.app:app"
check_process "python3 app/app.py"

echo "⏳ Waiting for processes to stop..."
sleep 3

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
git reset --hard origin/main || echo "⚠️ Git reset failed"
git pull origin main || echo "⚠️ Git pull failed"

# -----------------------------
# Install dependencies
# -----------------------------
echo "📦 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    $PIP install --user -r requirements.txt || {
        echo "⚠️ Installing missing packages individually..."
        $PIP install --user fastapi uvicorn python-multipart requests beautifulsoup4 python-dotenv fpdf pandas openpyxl lxml httpx slowapi
    }
else
    echo "⚠️ requirements.txt not found, installing basic packages..."
    $PIP install --user fastapi uvicorn python-multipart requests beautifulsoup4 python-dotenv fpdf pandas openpyxl lxml httpx slowapi
fi

# -----------------------------
# Verify installation
# -----------------------------
echo "🔍 Checking installation..."
$PYTHON -c "import fastapi, uvicorn; print('✅ Dependencies OK')" || {
    echo "❌ Dependency installation failed"
    exit 1
}

# -----------------------------
# Start the application
# -----------------------------
echo "🔥 Starting application..."
export PYTHONPATH=$PROJECT_DIR:$PYTHONPATH
echo "PYTHONPATH set to: $PYTHONPATH"

# Verify scraper module is importable
echo "🔍 Testing module imports..."
$PYTHON -c "from scraper import UltraScraper; print('✅ UltraScraper import OK')" || {
    echo "❌ UltraScraper import failed"
    exit 1
}

# Run Uvicorn in background and save logs
cd $PROJECT_DIR
$PYTHON -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 --access-log --log-level info > deployment.log 2>&1 &

APP_PID=$!
echo "📋 Application started with PID: $APP_PID"

sleep 5

# -----------------------------
# Check if application started
# -----------------------------
if kill -0 $APP_PID 2>/dev/null; then
    echo "✅ Application is running successfully (PID: $APP_PID)"
    echo "🌐 Server should be available at: http://YOUR_SERVER_IP/"

    # Restart systemd service if exists
    echo "🔄 Restarting ai-scraper service..."
    sudo systemctl restart ai-scraper || echo "⚠️ systemctl restart failed (service might not exist)"

    # Health check
    echo "🔍 Performing health check..."
    sleep 2
    if curl -f -s --max-time 10 http://localhost:8000/health > /dev/null; then
        echo "✅ Health check passed"
        echo "🎉 Deployment completed successfully!"
        exit 0
    else
        echo "❌ Health check failed"
        echo "📋 Last 20 lines of deployment.log:"
        tail -20 deployment.log
        exit 1
    fi
else
    echo "❌ Application failed to start"
    echo "📋 Last 20 lines of deployment.log:"
    tail -20 deployment.log
    exit 1
fi
