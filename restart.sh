#!/bin/bash

# Simple restart script for AI Scraper
echo "🔄 Restarting AI Scraper..."

# Kill existing processes
pkill -f "uvicorn app:app" || true
pkill -f "python app.py" || true

# Wait
sleep 2

# Start fresh
cd /home/ubuntu/Ai-scraper
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

echo "✅ Restart complete!"
