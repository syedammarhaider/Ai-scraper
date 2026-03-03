"""
AI SCRAPER - FULL WEBSITE CRAWLER WITH PRODUCT DETECTION
Professional grade web scraper with BFS crawling, product detection,
and multi-format export capabilities.

Author: AMMAR HAIDER
Version: 5.0 - Enterprise Edition
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
from scraper import UltraScraper  # Updated scraper with crawling capabilities
import os
import json
import time
import uuid
from typing import Optional
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging for production monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(title="AI Scraper Pro", version="5.0")

# Setup templates directory for HTML rendering
templates = Jinja2Templates(directory="templates")

# Initialize the enhanced scraper with crawling capabilities
scraper = UltraScraper()

# ---------- GROQ AI CONFIGURATION ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"  # Primary model for chat
MODEL_DEEP = "llama-3.3-70b-versatile"  # Model for deep analysis

# Initialize Groq client if API key is available
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ---------- HOME ROUTE ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main application interface"""
    logger.info("Home page accessed")
    return templates.TemplateResponse("index.html", {"request": request})

# ---------- HEALTH CHECK ----------
@app.get("/health")
async def health():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "version": "5.0",
        "timestamp": time.time()
    }

# ---------- FULL WEBSITE CRAWLER ----------
@app.post("/crawl")
async def crawl_website(request: Request):
    """
    Crawl entire website using BFS algorithm
    Automatically detects and extracts all products
    """
    form = await request.form()
    url = form.get("url")
    max_pages = int(form.get("max_pages", 100))  # Maximum pages to crawl
    delay = float(form.get("delay", 0.5))  # Delay between requests
    
    if not url:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "URL is required"}
        )
    
    # Ensure URL has protocol
    if not url.startswith("http"):
        url = "https://" + url
    
    logger.info(f"Starting crawl of {url} with max pages: {max_pages}")
    
    try:
        # Perform full website crawl with product detection
        result = scraper.crawl_website(
            start_url=url,
            max_pages=max_pages,
            delay=delay
        )
        
        if "error" in result:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": result["error"]}
            )
        
        logger.info(f"Crawl completed: {result['stats']['pages_crawled']} pages, {result['stats']['products_found']} products")
        
        return {
            "success": True,
            "data": result,
            "session_id": str(uuid.uuid4())
        }
        
    except Exception as e:
        logger.error(f"Crawl error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

# ---------- SINGLE PAGE SCRAPE (Legacy Support) ----------
@app.post("/scrape")
async def scrape_page(request: Request):
    """Scrape single page (backward compatibility)"""
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")
    
    if not url:
        return {"success": False, "error": "URL required"}
    
    if not url.startswith("http"):
        url = "https://" + url
    
    logger.info(f"Scraping single page: {url}")
    
    # Use the enhanced scraper's single page method
    data = scraper.scrape_website(url, mode)
    
    if "error" in data:
        return {"success": False, "error": data["error"]}
    
    return {"success": True, "data": data}

# ---------- CRAWL STATUS CHECK ----------
@app.get("/crawl-status/{session_id}")
async def crawl_status(session_id: str):
    """Get status of ongoing crawl session"""
    status = scraper.get_crawl_status(session_id)
    if not status:
        return {"success": False, "error": "Session not found"}
    
    return {"success": True, "status": status}

# ---------- GROQ CHAT (Scraped Data Analysis) ----------
@app.post("/groq-chat")
async def chat_with_data(request: Request):
    """
    AI chat using only scraped website data
    Strictly factual - no outside knowledge
    """
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not configured"}
    
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    
    if not message or not scraped:
        return {"success": False, "error": "Missing message or data"}
    
    try:
        data = json.loads(scraped)
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid scraped data format"}
    
    # System prompt enforcing strict data-only responses
    system_prompt = """
    You are an EXACT factual AI assistant.
    
    CRITICAL RULES:
    1. ONLY answer from the provided scraped website data
    2. If information is not in the data, say EXACTLY:
       "This information is not available in the scraped website data."
    3. Never use external knowledge or make assumptions
    4. Be concise and accurate
    5. Quote directly from the data when possible
    """
    
    # Prepare context with scraped data (limited to prevent token overflow)
    context = f"SCRAPED WEBSITE DATA:\n{json.dumps(data, indent=2)[:15000]}\n\nUSER QUESTION:\n{message}"
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.0,  # Zero temperature for maximum accuracy
            max_tokens=1500
        )
        
        answer = response.choices[0].message.content
        if not answer:
            answer = "No response generated."
        
        return {"success": True, "response": answer.strip()}
        
    except Exception as e:
        logger.error(f"Groq chat error: {str(e)}")
        return {"success": False, "error": f"AI service error: {str(e)}"}

# ---------- GROK MODE (Universal Knowledge) ----------
@app.post("/grok-mode")
async def grok_mode(request: Request):
    """
    Universal AI chat - can answer any question
    Uses AI's full knowledge base
    """
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not configured"}
    
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data", "{}")
    analysis_type = form.get("analysis_type", "comprehensive")
    
    if not message:
        return {"success": False, "error": "Message is required"}
    
    # System prompt for universal knowledge mode
    system_prompt = """
    You are GROK MODE - Advanced Universal AI Assistant.
    
    CAPABILITIES:
    - Answer ANY question using your comprehensive knowledge
    - Provide expert-level responses on any topic
    - Be helpful, accurate, and detailed
    - Use the scraped data as context if relevant, but you're not limited to it
    - Think step-by-step for complex questions
    - Provide examples and explanations when helpful
    """
    
    # Prepare context with scraped data for reference
    context = f"USER QUESTION:\n{message}\n\n"
    if scraped != "{}":
        context += f"Reference Website Data (for context only):\n{scraped[:5000]}\n\n"
    context += "Provide a comprehensive answer using your knowledge."
    
    try:
        response = client.chat.completions.create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.3,  # Slight creativity for better responses
            max_tokens=8000   # Extended for detailed answers
        )
        
        answer = response.choices[0].message.content
        return {"success": True, "response": answer.strip()}
        
    except Exception as e:
        logger.error(f"Grok mode error: {str(e)}")
        return {"success": False, "error": str(e)}

# ---------- EXPORT DATA ----------
@app.post("/export")
async def export_data(request: Request):
    """
    Export scraped/crawled data in various formats
    Supports: JSON, CSV, Excel, Text, PDF
    """
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")
    
    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}
    
    # Generate unique filename
    filename = f"export_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    # Map formats to handler methods
    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf,
        "markdown": scraper.save_as_markdown
    }
    
    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}
    
    try:
        file_path = handlers[fmt](data, filename)
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return {"success": False, "error": str(e)}

# ---------- START SERVER ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)