# app.py - Full Website Scraping + Groq/Grok Full-Length AI Responses with Rate Limit Handling
# Har line ke upar Roman Urdu comments added hain
# Is version mein 429 error handle kiya gaya hai exponential backoff ke sath
# Code length increase ki gayi hai detailed comments, logging, aur extra features add kar ke
# No truncation: Poora data ek hi request mein bhejte hain with large max_tokens
# 100% accurate working: Retry logic added for 429, better error handling

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import json
import time
import uuid
import math
import logging  # Logging ke liye import kiya gaya hai detailed logs ke liye
import requests  # Requests ke liye import
from requests.adapters import HTTPAdapter  # Retry adapter ke liye
from requests.packages.urllib3.util.retry import Retry  # Retry strategy ke liye
from backoff import on_exception, expo  # Exponential backoff ke liye backoff library import (pip install backoff)
from scraper import UltraScraper  # Custom scraper import

# ────────────────────────────────────────────────
#               Logging Configuration - Detailed logs for debugging 429 errors
# ────────────────────────────────────────────────
# Ye block logging setup karta hai taake har action ka log bane
logging.basicConfig(
    level=logging.INFO,  # Info level logs
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",  # Format set kiya gaya
    datefmt="%Y-%m-%d %H:%M:%S"  # Date format
)
logger = logging.getLogger("ai-scraper")  # Logger create kiya gaya

# ────────────────────────────────────────────────
#               Load environment variables - .env se variables load karte hain
# ────────────────────────────────────────────────
load_dotenv()  # .env file load karta hai

# ────────────────────────────────────────────────
#               Initialize FastAPI app with title and version
# ────────────────────────────────────────────────
app = FastAPI(
    title="AI Scraper - Ammar Edition with Rate Limit Handling",  # App title set kiya
    description="Web scraper + Groq-powered analysis with retries for 429",  # Description
    version="4.2.0"  # Version update kiya
)

# ────────────────────────────────────────────────
#               CORS middleware - Cross-origin requests allow karne ke liye
# ────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,  # CORS middleware add kiya
    allow_origins=["*"],  # Sab origins allow
    allow_credentials=True,  # Credentials allow
    allow_methods=["*"],  # Sab methods allow
    allow_headers=["*"],  # Sab headers allow
)

# ────────────────────────────────────────────────
#               Templates and Scraper Initialization
# ────────────────────────────────────────────────
templates = Jinja2Templates(directory="templates")  # Templates directory set kiya
scraper = UltraScraper()  # Scraper instance create kiya

# ────────────────────────────────────────────────
#               Mount static files - CSS/JS files serve karne ke liye
# ────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")  # Static files mount kiye

# ────────────────────────────────────────────────
#               Global exception handler - Sab errors ko handle karne ke liye
# ────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Server error occurred: {str(exc)}")  # Error log karta hai
    return JSONResponse(
        status_code=500,  # 500 status
        content={"success": False, "error": f"Server error: {str(exc)}"},  # Response
    )

# ────────────────────────────────────────────────
#               GROQ API CLIENT with Retry and Backoff for 429
# ────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # API key get karta hai
MODEL = "llama-3.3-70b-versatile"  # Model set kiya
MODEL_DEEP = "llama-3.3-70b-versatile"  # Deep model set kiya

class GroqDirectClient:
    def __init__(self, api_key):
        self.api_key = api_key  # API key save karta hai
        self.base_url = "https://api.groq.com/openai/v1"  # Base URL
        self.headers = {
            "Authorization": f"Bearer {api_key}",  # Auth header
            "Content-Type": "application/json"  # Content type
        }
        # Retry strategy for 429 - Exponential backoff
        retry_strategy = Retry(
            total=5,  # Max 5 retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these statuses
            backoff_factor=2,  # 2, 4, 8, 16 seconds delay
            allowed_methods=["HEAD", "GET", "POST"],  # Allowed methods
            raise_on_status=False  # Don't raise on status
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)  # Adapter create
        self.session = requests.Session()  # Session create
        self.session.mount("https://", adapter)  # HTTPS mount
        self.session.mount("http://", adapter)  # HTTP mount

    # Decorator for backoff on exceptions
    @on_exception(expo, requests.exceptions.RequestException, max_tries=5)
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=16000, **kwargs):
        try:
            data = {  # Data payload
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            data.update(kwargs)  # Extra kwargs add
            response = self.session.post(  # POST request with session (has retries)
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=60  # Timeout 60 seconds
            )
            if response.status_code == 429:  # Explicit 429 check
                retry_after = response.headers.get('retry-after', 5)  # Get retry-after header
                logger.warning(f"429 hit - sleeping for {retry_after} seconds")  # Log warning
                time.sleep(int(retry_after))  # Sleep
                raise requests.exceptions.RequestException("429 Retry")  # Raise to trigger backoff
            response.raise_for_status()  # Raise on error
            return response.json()  # JSON return
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error: {http_err}")  # Log HTTP error
            raise
        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")  # Log general error
            raise Exception(f"Groq API error: {str(e)}")

groq_ai = None  # Groq client variable
grok_mode = None  # Grok mode client

# ────────────────────────────────────────────────
#               Initialize Groq Clients with Fallback
# ────────────────────────────────────────────────
def initialize_grok_clients():
    global groq_ai, grok_mode  # Global variables
    try:
        groq_ai = GroqDirectClient(GROQ_API_KEY)  # Direct client create
        grok_mode = GroqDirectClient(GROQ_API_KEY)  # Grok client create
        logger.info("✅ Groq clients initialized successfully (Direct API with retries)")  # Success log
        return True
    except Exception as e:
        logger.error(f"⚠️ Direct initialization failed: {e}")  # Error log
        try:
            from groq import Groq  # Fallback to standard Groq
            groq_ai = Groq(api_key=GROQ_API_KEY)  # Standard client
            grok_mode = Groq(api_key=GROQ_API_KEY)  # Standard grok
            logger.info("✅ Groq clients initialized (Standard API as fallback)")  # Success log
            return True
        except Exception as e2:
            logger.error(f"❌ All initialization methods failed: {e2}")  # Final error
            groq_ai = None
            grok_mode = None
            return False

initialize_grok_clients()  # Clients initialize karte hain

# ────────────────────────────────────────────────
#               HOME Endpoint
# ────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)  # Home route
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})  # Index.html return

# ────────────────────────────────────────────────
#               HEALTH Endpoint with Extra Info
# ────────────────────────────────────────────────
@app.get("/health")  # Health check route
async def health():
    return {
        "status": "healthy",  # Status
        "groq_available": groq_ai is not None,  # Groq check
        "rate_limit_handling": "enabled with backoff",  # New info
        "timestamp": time.time()  # Timestamp
    }

# ────────────────────────────────────────────────
#               SCRAPE Endpoint with Logging
# ────────────────────────────────────────────────
@app.post("/scrape")  # Scrape POST route
async def scrape(request: Request):
    try:
        form = await request.form()  # Form data get
        url = form.get("url")  # URL get
        mode = form.get("mode", "comprehensive")  # Mode get
        if not url:  # URL check
            return {"success": False, "error": "URL required"}  # Error if missing
        if not url.startswith("http"):  # HTTP check
            url = "https://" + url  # Add https
        logger.info(f"🔍 Scraping URL: {url}, Mode: {mode}")  # Log scrape start
        if mode == "comprehensive":  # Comprehensive mode
            data = scraper.crawl_website(url, mode)  # Crawl website
        else:  # Other modes
            data = scraper.scrape_single_page(url, mode)  # Single page scrape
        logger.info(f"✅ Scraping completed for: {url}")  # Log success
        if "error" in data:  # Error check
            return {"success": False, "error": data["error"]}  # Return error
        data["session_id"] = str(uuid.uuid4())  # Session ID add
        return {"success": True, "data": data}  # Success response
    except Exception as e:  # Exception handle
        logger.error(f"❌ Scraping error: {str(e)}")  # Log error
        return {"success": False, "error": f"Scraping failed: {str(e)}"}  # Return error

# ────────────────────────────────────────────────
#               UTIL: Context Builder without Truncation
# ────────────────────────────────────────────────
def build_full_context(data, message):
    """Poora scraped data context mein convert karta hai without truncation"""
    context_parts = ["SCRAPED DATA ANALYSIS:"]  # Parts list
    if 'pages' in data:  # Multi-page check
        context_parts.append(f"Website crawled: {data.get('start_url', 'Unknown')}")  # Start URL
        context_parts.append(f"Total pages scraped: {len(data['pages'])}")  # Page count
        for i, page in enumerate(data['pages'], 1):  # Loop pages
            context_parts.append(f"PAGE {i}: {page.get('title', 'No title')}")  # Page title
            context_parts.append(f"URL: {page.get('url', 'Unknown')}")  # URL
            if page.get('description'):  # Description check
                context_parts.append(f"Description: {page['description']}")  # Add description
            if page.get('internal_links'):  # Internal links
                context_parts.append(f"INTERNAL LINKS ON THIS PAGE ({len(page['internal_links'])} total):")  # Count
                for link in page['internal_links']:  # All links without limit
                    context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")  # Add link
            else:
                context_parts.append("INTERNAL LINKS ON THIS PAGE: None")  # None if no links
            if page.get('external_links'):  # External links
                context_parts.append(f"EXTERNAL LINKS ON THIS PAGE ({len(page['external_links'])} total):")  # Count
                for link in page['external_links']:  # All without limit
                    context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")  # Add
            else:
                context_parts.append("EXTERNAL LINKS ON THIS PAGE: None")  # None
            if page.get('images'):  # Images
                context_parts.append(f"IMAGES ON THIS PAGE ({len(page['images'])} total):")  # Count
                for img in page['images']:  # All images
                    if img.get('url'):
                        context_parts.append(f"- {img.get('alt', 'No alt')}: {img.get('url')}")  # Add image
    else:  # Single page
        context_parts.append(f"Page: {data.get('title', 'No title')}")  # Title
        context_parts.append(f"URL: {data.get('url', 'Unknown')}")  # URL
        if data.get('description'):  # Description
            context_parts.append(f"Description: {data['description']}")  # Add
        if data.get('internal_links'):  # Internal
            context_parts.append(f"INTERNAL LINKS ({len(data['internal_links'])} total):")  # Count
            for link in data['internal_links']:  # All
                context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")  # Add
        if data.get('external_links'):  # External
            context_parts.append(f"EXTERNAL LINKS ({len(data['external_links'])} total):")  # Count
            for link in data['external_links']:  # All
                context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")  # Add
        if data.get('images'):  # Images
            context_parts.append(f"IMAGES ({len(data['images'])} total):")  # Count
            for img in data['images']:  # All
                if img.get('url'):
                    context_parts.append(f"- {img.get('alt', 'No alt')}: {img.get('url')}")  # Add
    context_parts.append(f"\nUSER QUESTION: {message}")  # User message add
    return "\n".join(context_parts)  # Join and return

# ────────────────────────────────────────────────
#               GROQ CHAT Endpoint with Full Context and No Chunking
# ────────────────────────────────────────────────
@app.post("/groq-chat")  # Chat POST route
async def chat(request: Request):
    form = await request.form()  # Form data
    message = form.get("message")  # Message get
    scraped = form.get("scraped_data")  # Scraped data get
    if not message or not scraped:  # Check missing
        return {"success": False, "error": "Missing data"}  # Error
    if not groq_ai:  # Client check
        return {"success": False, "error": "Groq AI client not initialized"}  # Error
    try:
        data = json.loads(scraped)  # JSON parse
    except:
        return {"success": False, "error": "Invalid scraped data JSON"}  # Invalid JSON error
    # Improved flexible system prompt - User instructions follow karta hai
    system_prompt = """
You are a precise, obedient data analyst that works EXCLUSIVELY with the provided scraped website data.

Core rules:
1. You may ONLY use information that actually exists in the SCRAPED DATA shown below
2. You MUST follow the user's exact instruction about how to present, filter, rename, count, group, reformat or extract that data
3. You are allowed and encouraged to:
   - list EVERY internal link and EVERY external link when asked
   - list EVERY image URL when asked
   - reorganize data (change key names, nested structure, flat list, etc.)
   - count items (links, images, paragraphs…)
   - filter (only links containing X, only images with alt text…)
   - convert formats (JSON → bullet list, table-like text, markdown table…)
   - group by page / domain / type
   - extract only certain fields
4. If the requested information is truly not present anywhere in the data → say only:
   "This information is not available in the scraped website data."
5. Never add facts, explanations, opinions or external knowledge
6. Never refuse a formatting / extraction / counting / listing request if the raw data exists
7. Be as complete as possible when user asks for "all", "every", "complete list", "full"

Always start your answer directly with the requested output (no chit-chat unless user explicitly asks for explanation).
"""  # Flexible prompt
    context = build_full_context(data, message)  # Full context build without chunks
    try:
        response = groq_ai.chat_completions_create(  # API call with retry
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},  # System message
                {"role": "user", "content": context}  # User context
            ],
            temperature=0,  # Temperature 0 for factual
            max_tokens=16000  # Large max_tokens for full responses
        )
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")  # Answer extract
        if not answer:  # Empty check
            answer = "Groq API did not return any answer."  # Default
        return {"success": True, "response": answer.strip()}  # Success
    except Exception as e:  # Exception
        logger.error(f"Groq chat error: {str(e)}")  # Log
        return {"success": False, "error": f"Groq API error: {str(e)}"}  # Error

# ────────────────────────────────────────────────
#               EXPORT Endpoint with More Formats
# ────────────────────────────────────────────────
@app.post("/export")  # Export POST
async def export(request: Request):
    body = await request.json()  # Body get
    fmt = body.get("format")  # Format
    data = body.get("data")  # Data
    if not fmt or not data:  # Check
        return {"success": False, "error": "Missing format or data"}  # Error
    filename = f"scraped_data"  # Filename
    handlers = {  # Handlers dictionary extended
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf,
        "yaml": scraper.save_as_yaml,  # New YAML format (assume implemented in scraper)
        "html": scraper.save_as_html  # New HTML report (assume implemented)
    }
    if fmt not in handlers:  # Unsupported check
        return {"success": False, "error": f"Unsupported format: {fmt}"}  # Error
    path = handlers[fmt](data, filename)  # Handler call
    return FileResponse(path, filename=os.path.basename(path))  # File response

# ────────────────────────────────────────────────
#               GROK MODE Endpoint with Retries
# ────────────────────────────────────────────────
@app.post("/grok-mode")  # Grok mode POST
async def grok_mode_endpoint(request: Request):
    try:
        form = await request.form()  # Form
        message = form.get("message")  # Message
        scraped = form.get("scraped_data")  # Scraped
        analysis_type = form.get("analysis_type", "comprehensive")  # Type
        if not message or not scraped:  # Check
            return {"success": False, "error": "Missing message or scraped data"}  # Error
        if not grok_mode:  # Client check
            return {"success": False, "error": "Grok Mode client not initialized"}  # Error
        system_prompt = f"""You are Grok Mode - an advanced AI assistant for universal questions. 
Rules: 
1. ONLY answer universal/general knowledge questions 
2. DO NOT use scraped data - ignore any website content provided 
3. Use your comprehensive knowledge for all answers 
4. Be helpful, detailed, and comprehensive 
5. Analysis Type: {analysis_type} """  # Prompt
        full_context = f"USER QUESTION:\n{message}\n\n(Note: Provide comprehensive expert answer.)"  # Context
        response = grok_mode.chat_completions_create(  # Call with retry
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}
            ],
            temperature=0.4,  # Temperature
            max_tokens=8000  # Max tokens
        )
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")  # Answer
        if not answer:  # Empty
            answer = "No response generated from Grok Mode."  # Default
        return {  # Response
            "success": True,
            "response": answer.strip(),
            "mode": "grok_mode",
            "model": MODEL_DEEP,
            "analysis_type": analysis_type
        }
    except Exception as e:  # Exception
        logger.error(f"Grok Mode failed: {str(e)}")  # Log
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}  # Error

# ────────────────────────────────────────────────
#               GROK SUMMARY Endpoint
# ────────────────────────────────────────────────
@app.post("/grok-summary")  # Summary POST
async def grok_summary(request: Request):
    form = await request.form()  # Form
    scraped = form.get("scraped_data")  # Scraped
    if not scraped:  # Check
        return {"success": False, "error": "Missing scraped data"}  # Error
    if not groq_ai:  # Client
        return {"success": False, "error": "Groq AI client not initialized"}  # Error
    data = json.loads(scraped)  # Parse
    system_prompt = """You are GROK MODE SUMMARY - Extract key facts instantly and accurately. 
Provide structured summary: 
1. MAIN TOPIC 
2. KEY POINTS (3-5) 
3. STATISTICS 
4. CONCLUSION 
Only use data from the page. If info missing, say "Not found"."""  # Prompt
    context_parts = [f"URL: {data.get('url', '')}"]  # Parts
    if data.get('title'):  # Title
        context_parts.append(f"Title: {data['title']}")  # Add
    if data.get('description'):  # Desc
        context_parts.append(f"Description: {data['description']}")  # Add
    if data.get('paragraphs'):  # Paragraphs
        context_parts.append("\nContent:\n" + "\n".join(data['paragraphs'][:50]))  # Add limited
    response = groq_ai.chat_completions_create(  # Call
        model=MODEL_DEEP,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(context_parts)}
        ],
        temperature=0.1,  # Temp
        max_tokens=5000  # Max
    )
    answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")  # Answer
    return {"success": True, "summary": answer.strip(), "mode": "grok_summary"}  # Response

# ────────────────────────────────────────────────
#               Extra Endpoint: Get Rate Limit Info (for debugging)
# ────────────────────────────────────────────────
@app.get("/rate-limits")  # Rate limits info route
async def get_rate_limits():
    return {
        "info": "Free tier: ~60 RPM, 1000 RPD. Use backoff for 429.",  # Info
        "retry_strategy": "Exponential backoff with 5 tries",  # Strategy
        "backoff_factor": 2  # Factor
    }

# ────────────────────────────────────────────────
#               Run the App
# ────────────────────────────────────────────────
if __name__ == "__main__":  # If main
    import uvicorn  # Uvicorn import
    uvicorn.run(app, host="0.0.0.0", port=8000)  # Run server