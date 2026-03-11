# Export app from app.py for uvicorn module loading
# This fixes: "Attribute 'app' not found in module 'app'"
from app.app import app
from app.app import scraper
from app.app import gemini_client
