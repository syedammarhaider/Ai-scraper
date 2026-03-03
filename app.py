# app.py - FastAPI backend for AI SCRAPER
# Yeh file web server hai jo frontend requests handle karta hai

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from scraper import UltraScraper
import os
import json
import time
import uuid
import requests
from datetime import datetime

# Environment variables load karo (.env file se)
load_dotenv()

# FastAPI app initialize karo
app = FastAPI(title="AI SCRAPER - Professional Edition")

# Templates folder set karo
templates = Jinja2Templates(directory="templates")

# Static files serve karo (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Scraper instance create karo
scraper = UltraScraper()

# Groq API setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Direct Groq client using requests (Python 3.14 compatible)
class GroqDirectClient:
    """Direct Groq API client using requests library"""
    
    def __init__(self, api_key):
        """Initialize client with API key"""
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500, **kwargs):
        """Send chat completion request to Groq API"""
        try:
            data = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            data.update(kwargs)
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=60  # 60 seconds timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")

# Initialize Groq clients
groq_ai = None
grok_mode = None

if GROQ_API_KEY:
    try:
        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode = GroqDirectClient(GROQ_API_KEY)
        print("✅ Groq clients initialized successfully")
    except Exception as e:
        print(f"⚠️ Groq initialization failed: {e}")
        groq_ai = None
        grok_mode = None
else:
    print("⚠️ GROQ_API_KEY not found in .env file")

# ---------- HOME PAGE ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main HTML page"""
    return templates.TemplateResponse("index.html", {"request": request})

# ---------- HEALTH CHECK ----------
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "4.0",
        "groq_available": groq_ai is not None
    }

# ---------- SCRAPE ENDPOINT ----------
@app.post("/scrape")
async def scrape(request: Request):
    """
    Scrape website endpoint
    Form data: url, mode (basic/smart/comprehensive), max_pages, max_products
    """
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")
        
        # Get max pages and products from form (with defaults)
        try:
            max_pages = int(form.get("max_pages", 500))
        except:
            max_pages = 500
            
        try:
            max_products = int(form.get("max_products", 5000))
        except:
            max_products = 5000
        
        # Validate URL
        if not url:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "URL is required"}
            )
        
        # Add protocol if missing
        if not url.startswith("http"):
            url = "https://" + url
        
        print(f"\n{'='*60}")
        print(f"📥 SCRAPE REQUEST RECEIVED")
        print(f"📌 URL: {url}")
        print(f"⚙️ Mode: {mode}")
        print(f"📊 Max Pages: {max_pages}")
        print(f"📦 Max Products: {max_products}")
        print(f"{'='*60}\n")
        
        # Start scraping
        start_time = time.time()
        result = scraper.scrape_website(url, mode, max_pages, max_products)
        
        # Check for errors
        if "error" in result:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": result["error"]}
            )
        
        # Add session ID
        result["session_id"] = str(uuid.uuid4())
        
        # Calculate time
        result["stats"]["total_time"] = round(time.time() - start_time, 2)
        
        print(f"\n{'='*60}")
        print(f"✅ SCRAPE COMPLETED")
        print(f"📦 Total Products: {result.get('total_products', 0)}")
        print(f"⏱️ Time: {result['stats']['scrape_time']} seconds")
        print(f"{'='*60}\n")
        
        return {"success": True, "data": result}
    
    except Exception as e:
        print(f"❌ Scrape error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Scraping failed: {str(e)}"}
        )

# ---------- GROQ CHAT ENDPOINT ----------
@app.post("/groq-chat")
async def groq_chat(request: Request):
    """
    Chat with scraped data using Groq
    """
    try:
        form = await request.form()
        message = form.get("message")
        scraped_data = form.get("scraped_data")
        
        if not message or not scraped_data:
            return {"success": False, "error": "Missing message or scraped data"}
        
        if not groq_ai:
            return {"success": False, "error": "Groq AI not available"}
        
        # Parse scraped data
        try:
            data = json.loads(scraped_data)
        except:
            return {"success": False, "error": "Invalid scraped data format"}
        
        # Prepare context
        products = data.get('products', [])
        total_products = data.get('total_products', 0)
        
        # Create a summary of the data
        summary = f"""
Website: {data.get('url', 'Unknown')}
Total Products Found: {total_products}
Pages Scraped: {data.get('stats', {}).get('pages_scraped', 0)}

Product Categories Found: {len(set([p.get('category', '') for p in products if p.get('category')]))}
Products with Prices: {len([p for p in products if p.get('price')])}
Products with Images: {len([p for p in products if p.get('image')])}

Sample Products (first 5):
"""
        
        for i, p in enumerate(products[:5]):
            price = f"${p.get('price')}" if p.get('price') else "Price N/A"
            summary += f"\n{i+1}. {p.get('name', 'Unknown')} - {price}"
        
        # System prompt
        system_prompt = """You are an AI assistant that analyzes scraped website data.
You have been given data from a website scrape containing multiple products.
Answer questions based ONLY on this data. If information is not in the data, say so.
Be precise, helpful, and factual. Provide statistics when relevant."""
        
        # User message with context
        user_message = f"""
SCRAPED DATA SUMMARY:
{summary}

Full data has {total_products} products.

USER QUESTION: {message}

Please answer based on the scraped data above.
"""
        
        # Call Groq API
        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        return {"success": True, "response": answer}
    
    except Exception as e:
        print(f"❌ Groq chat error: {str(e)}")
        return {"success": False, "error": f"Chat error: {str(e)}"}

# ---------- GROK MODE ENDPOINT ----------
@app.post("/grok-mode")
async def grok_mode(request: Request):
    """
    Universal AI chat (not limited to scraped data)
    """
    try:
        form = await request.form()
        message = form.get("message")
        scraped_data = form.get("scraped_data", "{}")
        
        if not message:
            return {"success": False, "error": "Missing message"}
        
        if not grok_mode:
            return {"success": False, "error": "Grok Mode not available"}
        
        # Parse scraped data (optional context)
        try:
            data = json.loads(scraped_data)
            has_data = bool(data.get('products'))
        except:
            data = {}
            has_data = False
        
        # System prompt for universal mode
        system_prompt = """You are GROK MODE - an advanced AI assistant for universal questions.
You can answer ANY question using your general knowledge.
Be helpful, detailed, and comprehensive in your responses.
Provide accurate information and cite sources when possible."""
        
        # Build context
        if has_data and len(data.get('products', [])) > 0:
            context = f"""
Website context available (scraped data contains {len(data.get('products', []))} products).
However, you are NOT limited to this data. Use your universal knowledge.

USER QUESTION: {message}

Please provide a comprehensive answer using your general knowledge.
"""
        else:
            context = f"""
USER QUESTION: {message}

Please provide a comprehensive answer using your general knowledge.
"""
        
        # Call Groq API
        response = grok_mode.chat_completions_create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.5,
            max_tokens=8000  # Long answers
        )
        
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        return {"success": True, "response": answer}
    
    except Exception as e:
        print(f"❌ Grok mode error: {str(e)}")
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}

# ---------- EXPORT ENDPOINT ----------
@app.post("/export")
async def export_data(request: Request):
    """
    Export scraped data in various formats
    """
    try:
        body = await request.json()
        export_format = body.get("format")
        data = body.get("data")
        filename = body.get("filename", f"scraped_{int(time.time())}")
        
        if not export_format or not data:
            return {"success": False, "error": "Missing format or data"}
        
        # Create exports directory if not exists
        if not os.path.exists("exports"):
            os.makedirs("exports")
        
        # Export based on format
        if export_format == "json":
            filepath = os.path.join("exports", f"{filename}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        elif export_format == "csv":
            filepath = os.path.join("exports", f"{filename}.csv")
            # Simple CSV export
            products = data.get('products', [])
            if products:
                import csv
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=products[0].keys())
                    writer.writeheader()
                    writer.writerows(products)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("No products found")
        
        elif export_format == "txt":
            filepath = os.path.join("exports", f"{filename}.txt")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"URL: {data.get('url', 'N/A')}\n")
                f.write(f"Total Products: {data.get('total_products', 0)}\n")
                f.write(f"Scraped At: {data.get('scraped_at', 'N/A')}\n\n")
                for i, p in enumerate(data.get('products', []), 1):
                    f.write(f"{i}. {p.get('name', 'Unknown')}\n")
                    if p.get('price'):
                        f.write(f"   Price: ${p['price']}\n")
                    if p.get('url'):
                        f.write(f"   URL: {p['url']}\n")
                    f.write("\n")
        
        else:
            return {"success": False, "error": f"Unsupported format: {export_format}"}
        
        return FileResponse(
            path=filepath,
            filename=os.path.basename(filepath),
            media_type='application/octet-stream'
        )
    
    except Exception as e:
        print(f"❌ Export error: {str(e)}")
        return {"success": False, "error": f"Export failed: {str(e)}"}

# ---------- STATUS ENDPOINT ----------
@app.get("/status/{session_id}")
async def get_status(session_id: str):
    """Get scraping status for a session"""
    # This is a placeholder - implement actual status tracking if needed
    return {
        "session_id": session_id,
        "status": "completed",
        "timestamp": datetime.now().isoformat()
    }