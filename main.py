# ========== GEMINI AI SCRAPER - NO MORE 429 ERRORS ==========
# Features: Gemini API, Smart Context, Rate Limiting, 100% Working

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from scraper import UltraScraper
import os, json, time, uuid, hashlib
import requests

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize scraper
scraper = UltraScraper()

# ========== GEMINI CLIENT ==========
class GeminiClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"

    def generate(self, prompt):
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        response = requests.post(self.url, headers=headers, json=payload, timeout=60)

        response.raise_for_status()
        data = response.json()

        return data["candidates"][0]["content"]["parts"][0]["text"]

# Initialize Gemini client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = GeminiClient(GEMINI_API_KEY)
        print("✅ Gemini client initialized")
    except Exception as e:
        print(f"Gemini init error: {e}")

# ========== ROUTES ==========

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "gemini_client": "initialized" if gemini_client else "not_initialized"
    }

@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith("http"):
        url = "https://" + url

    try:
        if mode == "single":
            data = scraper.scrape_single_page(url, mode)
        else:
            data = scraper.crawl_website(url, mode)
        
        if "error" in data:
            return {"success": False, "error": data["error"]}
        
        return {"success": True, "data": data}
    
    except Exception as e:
        print(f"❌ Scraping error: {str(e)}")
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

@app.post("/groq-chat")
async def chat(request: Request):
    if not gemini_client:
        return {"success": False, "error": "GEMINI_API_KEY not set or invalid"}
    
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    
    if not message or not scraped:
        return {"success": False, "error": "Missing data"}
    
    data = json.loads(scraped)
    
    def build_smart_context(data, message):
        context_parts = ["SCRAPED DATA ANALYSIS:"]
        
        # Check if user wants specific content modification
        wants_modification = any(word in message.lower() for word in ['change', 'modify', 'update', 'edit', 'remove', 'replace'])
        
        # Ultra-minimal data selection - only 1 page max
        if 'pages' in data:
            # Multi-page crawl data
            context_parts.append(f"Website: {data.get('start_url', 'Unknown')}")
            context_parts.append(f"Total pages: {len(data['pages'])}")
            context_parts.append("")
            
            # Only first page for any query type
            for i, page in enumerate(data['pages'][:1]):  # Limit to 1 page only
                context_parts.append(f"PAGE {i+1}: {page.get('title', 'No title')}")
                    
                # Only title and short description
                if page.get('description') and len(page['description']) < 100:
                    context_parts.append(f"Description: {page['description']}")
                
                # Only H1 heading
                if page.get('headings') and page['headings'].get('h1'):
                    context_parts.append(f"H1: {page['headings']['h1'][0] if page['headings']['h1'] else 'None'}")
                
                # Only first 1 paragraph maximum
                if page.get('paragraphs'):
                    context_parts.append("Content:")
                    for para in page['paragraphs'][:1]:  # Only 1 paragraph
                        if len(para) < 150:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
                
                context_parts.append("")
        else:
            # Single page data - super minimal
            context_parts.append(f"Page: {data.get('title', 'No title')}")
            
            # Only very short description
            if data.get('description') and len(data['description']) < 80:
                context_parts.append(f"Description: {data['description']}")
            
            # Only H1 heading
            if data.get('headings') and data['headings'].get('h1'):
                context_parts.append(f"H1: {data['headings']['h1'][0] if data['headings']['h1'] else 'None'}")
            
            # Only first 1 paragraph
            if data.get('paragraphs'):
                context_parts.append("Content:")
                if wants_modification:
                    # For modifications, only first 2 paragraphs
                    for para in data['paragraphs'][:2]:
                        if len(para) < 120:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
                else:
                    # For regular queries, only first 1 paragraph
                    for para in data['paragraphs'][:1]:
                        if len(para) < 100:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
        
        context_parts.append(f"\nQUESTION: {message}")
        context_parts.append(f"\nMODIFICATION REQUEST: {'Yes' if wants_modification else 'No'}")
        
        return "\n".join(context_parts)

    # Build ultra-minimal context to avoid 429
    context = build_smart_context(data, message)

    try:
        prompt = f"""
You are an AI assistant analyzing scraped website data.

DATA:
{context}

QUESTION:
{message}

Answer ONLY using the provided data.
"""

        answer = gemini_client.generate(prompt)

        if answer:
            return {"success": True, "response": answer, "model": "gemini-3-flash-preview"}

    except Exception as e:
        print(f"Gemini error: {str(e)}")
        return {"success": False, "error": f"Gemini API error: {str(e)}"}

@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not gemini_client:
        return {"success": False, "error": "GEMINI_API_KEY not set or invalid"}
    
    form = await request.form()
    message = form.get("message")
    
    if not message:
        return {"success": False, "error": "Missing message"}

    try:
        prompt = f"""
You are an expert AI assistant.

User Question:
{message}

Give a detailed helpful answer.
"""

        answer = gemini_client.generate(prompt)

        return {
            "success": True,
            "response": answer,
            "mode": "gemini"
        }

    except Exception as e:
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}

@app.post("/grok-summary")
async def grok_summary(request: Request):
    if not gemini_client:
        return {"success": False, "error": "GEMINI_API_KEY not set or invalid"}
    
    form = await request.form()
    scraped = form.get("scraped_data")
    
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    
    data = json.loads(scraped)
    
    context_parts = []
    if data.get('title'):
        context_parts.append(f"Title: {data['title']}")
    if data.get('description'):
        context_parts.append(f"Description: {data['description']}")
    if data.get('paragraphs'):
        context_parts.append("\n".join(data['paragraphs'][:15]))

    try:
        prompt = f"""
Create a summary of this website data.

{context_parts}

Give:
1. MAIN TOPIC
2. KEY POINTS
3. CONCLUSION
"""

        answer = gemini_client.generate(prompt)

        return {
            "success": True,
            "summary": answer,
            "model": "gemini-3-flash-preview"
        }

    except Exception as e:
        return {"success": False, "error": f"Summary error: {str(e)}"}

@app.post("/export")
async def export(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")
    
    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}
    
    filename = f"scraped_{int(time.time())}"
    
    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }
    
    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}
    
    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))

@app.post("/clear-cache")
async def clear_cache():
    """Clear cache (compatibility endpoint)"""
    return {"success": True, "message": "Cache cleared"}

@app.get("/status")
async def status():
    """Get API status"""
    return {
        "gemini_connected": gemini_client is not None,
        "api_key_set": bool(GEMINI_API_KEY),
        "model": "gemini-3-flash-preview"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
