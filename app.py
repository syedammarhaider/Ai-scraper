"""
AI SCRAPER PRO - ULTIMATE EDITION
100% Working | Ultra Fast | Zero Errors
Author: AMMAR HAIDER
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from groq import Groq
from scraper import UltraScraper
import os
import json
import time
import uuid
import logging
import traceback

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="AI Scraper Pro")

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize scraper
scraper = UltraScraper()

# Groq AI
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ========== HOME ROUTE ==========
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main page"""
    return templates.TemplateResponse("index.html", {"request": request})

# ========== HEALTH CHECK ==========
@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "time": time.time()}

# ========== CRAWL WEBSITE ==========
@app.post("/crawl")
async def crawl_website(request: Request):
    """Crawl entire website - FAST"""
    try:
        form = await request.form()
        url = form.get("url", "").strip()
        max_pages = int(form.get("max_pages", 50))  # Default 50 for speed
        delay = float(form.get("delay", 0.2))  # Fast crawling
        
        if not url:
            return JSONResponse(status_code=400, content={"success": False, "error": "URL required"})
        
        # Add https:// if missing
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        logger.info(f"Crawling: {url}")
        
        # FAST CRAWL - Limited pages for speed
        result = scraper.crawl_website(url, max_pages=min(max_pages, 50), delay=delay)
        
        if "error" in result:
            return JSONResponse(status_code=500, content={"success": False, "error": result["error"]})
        
        return {"success": True, "data": result, "session_id": str(uuid.uuid4())}
        
    except Exception as e:
        logger.error(f"Crawl error: {str(e)}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# ========== SCRAPE SINGLE PAGE ==========
@app.post("/scrape")
async def scrape_page(request: Request):
    """Scrape single page - ULTRA FAST"""
    try:
        form = await request.form()
        url = form.get("url", "").strip()
        
        if not url:
            return {"success": False, "error": "URL required"}
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # Fast single page scrape
        data = scraper.scrape_website_fast(url)
        
        if "error" in data:
            return {"success": False, "error": data["error"]}
        
        return {"success": True, "data": data}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== GROQ CHAT ==========
@app.post("/groq-chat")
async def groq_chat(request: Request):
    """AI chat with scraped data"""
    if not client:
        return {"success": False, "error": "GROQ_API_KEY missing"}
    
    try:
        form = await request.form()
        message = form.get("message", "").strip()
        scraped = form.get("scraped_data", "{}")
        
        if not message:
            return {"success": False, "error": "Message required"}
        
        data = json.loads(scraped) if scraped != "{}" else {}
        
        # Simple prompt for speed
        prompt = f"DATA: {json.dumps(data)[:5000]}\n\nQ: {message}\nA: Answer from data only."
        
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Faster model
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500
        )
        
        return {"success": True, "response": response.choices[0].message.content}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== GROK MODE ==========
@app.post("/grok-mode")
async def grok_mode(request: Request):
    """Universal AI chat"""
    if not client:
        return {"success": False, "error": "GROQ_API_KEY missing"}
    
    try:
        form = await request.form()
        message = form.get("message", "").strip()
        
        if not message:
            return {"success": False, "error": "Message required"}
        
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Fast model
            messages=[{"role": "user", "content": message}],
            temperature=0.3,
            max_tokens=1000
        )
        
        return {"success": True, "response": response.choices[0].message.content}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== EXPORT ==========
@app.post("/export")
async def export_data(request: Request):
    """Export data - FAST"""
    try:
        body = await request.json()
        fmt = body.get("format", "json")
        data = body.get("data", {})
        
        if not data:
            return {"success": False, "error": "No data"}
        
        filename = f"export_{int(time.time())}"
        
        # Fast export handlers
        if fmt == "json":
            path = scraper.save_as_json(data, filename)
        elif fmt == "csv":
            path = scraper.save_as_csv(data, filename)
        elif fmt == "excel":
            path = scraper.save_as_excel(data, filename)
        elif fmt == "txt":
            path = scraper.save_as_text(data, filename)
        elif fmt == "pdf":
            path = scraper.save_as_pdf(data, filename)
        elif fmt == "markdown":
            path = scraper.save_as_markdown(data, filename)
        else:
            return {"success": False, "error": f"Unknown format: {fmt}"}
        
        return FileResponse(path, filename=os.path.basename(path))
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== RUN ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)