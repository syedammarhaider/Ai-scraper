#!/bin/bash

# Deployment script for AI Scraper
echo "🚀 Starting deployment..."

# Kill any existing processes
pkill -f "uvicorn app:app" || true
pkill -f "python app.py" || true

# Wait for processes to stop
sleep 2

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt || {
    echo "Installing missing packages..."
    pip install fastapi uvicorn python-multipart requests beautifulsoup4 python-dotenv fpdf pandas openpyxl
}

# Change to project directory
cd /home/ubuntu/Ai-scraper

# Start the application
echo "🔥 Starting application..."
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

echo "✅ Deployment complete!"
