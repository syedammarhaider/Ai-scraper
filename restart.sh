#!/bin/bash

# Simple restart script for AI Scraper with git reset
echo "🔄 Restarting AI Scraper..."

# Navigate to project directory
cd /home/ubuntu/Ai-scraper

# Reset to previous commit (as requested)
echo "🔄 Resetting to previous commit..."
git reset --hard HEAD~1 || echo "⚠️ Git reset failed"

# Kill existing processes
pkill -f "uvicorn app:app" || true
pkill -f "python app.py" || true

# Wait
sleep 2

# Start fresh
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

# Restart ai-scraper service (as requested)
echo "🔄 Restarting ai-scraper service..."
sudo systemctl restart ai-scraper || echo "⚠️ systemctl restart failed"

echo "✅ Restart complete!"
