#!/bin/bash

# Robust deployment script for AI Scraper
set -e  # Exit on any error

echo "🚀 Starting deployment..."

# Function to check if process is running
check_process() {
    if pgrep -f "$1" > /dev/null; then
        echo "❌ Process $1 is running, killing..."
        pkill -f "$1" || true
        sleep 2
    fi
}

# Kill existing processes
check_process "uvicorn app:app"
check_process "python app.py"

# Wait for processes to stop
echo "⏳ Waiting for processes to stop..."
sleep 3

# Change to project directory
cd /home/ubuntu/Ai-scraper || {
    echo "❌ Cannot change to project directory"
    exit 1
}

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo "❌ app.py not found"
    exit 1
fi

# Install dependencies with error handling
echo "📦 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt || {
        echo "⚠️ Installing missing packages individually..."
        pip install fastapi uvicorn python-multipart requests beautifulsoup4 python-dotenv fpdf pandas openpyxl lxml urllib3
    }
else
    echo "⚠️ requirements.txt not found, installing basic packages..."
    pip install fastapi uvicorn python-multipart requests beautifulsoup4 python-dotenv fpdf pandas openpyxl lxml urllib3
fi

# Check if installation was successful
echo "🔍 Checking installation..."
python -c "import fastapi, uvicorn; print('✅ Dependencies OK')" || {
    echo "❌ Dependency installation failed"
    exit 1
}

# Start the application with error handling
echo "🔥 Starting application..."
export PYTHONPATH=/home/ubuntu/Ai-scraper:$PYTHONPATH

# Try to start application
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 --access-log --log-level info > deployment.log 2>&1 &

# Get the PID
APP_PID=$!
echo "📋 Application started with PID: $APP_PID"

# Wait a moment and check if it's still running
sleep 5

if kill -0 $APP_PID 2>/dev/null; then
    echo "✅ Application is running successfully (PID: $APP_PID)"
    echo "🌐 Server should be available at: http://3.95.32.144/"
    
    # Health check
    echo "🔍 Performing health check..."
    sleep 2
    
    if curl -f -s --max-time 10 http://localhost:8000/health > /dev/null; then
        echo "✅ Health check passed"
        echo "🎉 Deployment completed successfully!"
        exit 0
    else
        echo "❌ Health check failed"
        echo "📋 Checking logs..."
        tail -20 deployment.log
        exit 1
    fi
else
    echo "❌ Application failed to start"
    echo "📋 Checking logs..."
    tail -20 deployment.log
    exit 1
fi
