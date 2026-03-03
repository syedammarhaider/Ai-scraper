# app.py - Main FastAPI application
# Yeh FastAPI framework hai jo backend server ko control karta hai
# Isme routes define hain aur AI chat functionality

from fastapi import FastAPI, Request  # FastAPI for web server, Request for handling HTTP requests
from fastapi.responses import HTMLResponse, FileResponse  # HTMLResponse for serving HTML, FileResponse for file downloads
from fastapi.templating import Jinja2Templates  # Jinja2Templates for rendering HTML templates
from dotenv import load_dotenv  # Load environment variables from .env file
from scraper import UltraScraper  # Our custom scraper class
import os  # Operating system functions (file paths, env vars)
import json  # JSON handling for data
import time  # Time functions for timestamps
import uuid  # Generate unique IDs
import requests  # HTTP requests for API calls

# Load .env file variables (GROQ_API_KEY)
load_ddotenv()

# Initialize FastAPI app
app = FastAPI()

# Setup templates directory for HTML files
templates = Jinja2Templates(directory="templates")

# Initialize our scraper
scraper = UltraScraper()

# Groq API Key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Models for AI responses
MODEL = "llama-3.3-70b-versatile"  # Main model
MODEL_DEEP = "llama-3.3-70b-versatile"  # Deep model for Grok mode

# ========== DIRECT GROQ CLIENT ==========
# Direct API client for maximum compatibility
class GroqDirectClient:
    """Direct Groq API client without external library issues"""
    
    def __init__(self, api_key):
        # Constructor - initialize with API key
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500, **kwargs):
        """Send chat completion request to Groq API"""
        try:
            # Prepare request data
            data = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            data.update(kwargs)  # Add any extra parameters
            
            # Send POST request to Groq API
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30  # 30 second timeout
            )
            response.raise_for_status()  # Raise error if request failed
            return response.json()  # Return JSON response
            
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")

# Initialize Groq clients
groq_ai = GroqDirectClient(GROQ_API_KEY) if GROQ_API_KEY else None
grok_mode = GroqDirectClient(GROQ_API_KEY) if GROQ_API_KEY else None

# ========== HOME ROUTE ==========
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main HTML page"""
    return templates.TemplateResponse("index.html", {"request": request})

# ========== HEALTH CHECK ==========
@app.get("/health")
async def health():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "timestamp": time.time()}

# ========== SCRAPE ENTIRE WEBSITE ==========
@app.post("/scrape-full-site")
async def scrape_full_site(request: Request):
    """Scrape entire website - all pages, all products"""
    try:
        # Get form data from request
        form = await request.form()
        start_url = form.get("url")  # Starting URL
        max_pages = int(form.get("max_pages", 100))  # Maximum pages to scrape
        mode = form.get("mode", "comprehensive")  # Scraping mode
        
        if not start_url:
            return {"success": False, "error": "URL required"}
        
        # Add https if missing
        if not start_url.startswith("http"):
            start_url = "https://" + start_url
        
        print(f"🔍 Starting full site scrape: {start_url}, Max pages: {max_pages}")
        
        # Call full site scraper
        result = scraper.scrape_full_website(
            start_url=start_url,
            max_pages=max_pages,
            mode=mode
        )
        
        if "error" in result:
            return {"success": False, "error": result["error"]}
        
        # Add session ID for frontend
        result["session_id"] = str(uuid.uuid4())
        
        print(f"✅ Full site scrape complete: {result['stats']['pages_scraped']} pages, {result['stats']['total_products']} products")
        
        return {"success": True, "data": result}
        
    except Exception as e:
        print(f"❌ Full site scrape error: {str(e)}")
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

# ========== SCRAPE SINGLE PAGE ==========
@app.post("/scrape")
async def scrape(request: Request):
    """Scrape single page (backward compatibility)"""
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        print(f"🔍 Scraping single URL: {url}, Mode: {mode}")
        data = scraper.scrape_website(url, mode)
        
        if "error" in data: 
            return {"success": False, "error": data["error"]}
        
        # Add session_id for frontend
        data["session_id"] = data.get("scrape_id", str(uuid.uuid4()))
        return {"success": True, "data": data}
    
    except Exception as e:
        print(f"❌ Scraping error: {str(e)}")
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

# ========== GROQ CHAT ==========
@app.post("/groq-chat")
async def chat(request: Request):
    """Chat with AI about scraped data"""
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    
    if not message or not scraped:
        return {"success": False, "error": "Missing data"}
    if not groq_ai:
        return {"success": False, "error": "Groq AI client not initialized"}

    data = json.loads(scraped)
    
    # System prompt - strict rules for answering
    system_prompt = """
You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
5. For greetings, respond naturally but briefly.
"""
    # Context with scraped data
    context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:8000]}\n\nQUESTION:\n{message}"

    try:
        # Send request to Groq
        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0,
            max_tokens=1500
        )
        # Extract answer from response
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No answer returned").strip()
        return {"success": True, "response": answer}
        
    except Exception as e:
        return {"success": False, "error": f"Groq API error: {str(e)}"}

# ========== GROK MODE ==========
@app.post("/grok-mode")
async def grok_mode_endpoint(request: Request):
    """Grok Mode - Enhanced AI for universal questions"""
    try:
        form = await request.form()
        message = form.get("message")
        scraped = form.get("scraped_data")  # Optional, might be used for context
        
        if not message:
            return {"success": False, "error": "Missing message"}
        if not grok_mode:
            return {"success": False, "error": "Grok Mode client not initialized"}
        
        # Grok Mode system prompt - uses universal knowledge
        system_prompt = """You are Grok Mode - an advanced AI assistant.
You have access to universal knowledge and can answer ANY question.
Be comprehensive, detailed, and helpful.
Provide expert-level answers with depth and clarity."""

        try:
            # Send request to Grok
            response = grok_mode.chat_completions_create(
                model=MODEL_DEEP,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                temperature=0.4,
                max_tokens=8000  # Long responses
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No response generated.")
            
            return {
                "success": True, 
                "response": answer.strip(),
                "mode": "grok_mode"
            }
            
        except Exception as e:
            return {"success": False, "error": f"Grok Mode error: {str(e)}"}
    
    except Exception as e:
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}

# ========== EXPORT DATA ==========
@app.post("/export")
async def export(request: Request):
    """Export scraped data in various formats"""
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

    filename = f"scraped_data_{int(time.time())}"

    # Export handlers dictionary
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

    # Call the export function
    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))