from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
# from groq import Groq  # Temporarily disabled for Python 3.14 compatibility
from scraper import UltraScraper
import os, json, time, uuid

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# GROQ - Using direct API calls for Python 3.14 compatibility
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"  # Using supported model for Grok Mode

# Direct Groq API client using requests for better compatibility
import requests

class GroqDirectClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500, **kwargs):
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
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")

# Global variables for Groq clients
groq_ai = None
grok_mode = None

# Initialize Groq clients with robust error handling
def initialize_grok_clients():
    """Initialize both Groq AI and Grok Mode clients with error handling"""
    global groq_ai, grok_mode
    
    try:
        # Try direct initialization first (most compatible)
        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode = GroqDirectClient(GROQ_API_KEY)
        print("✅ Groq clients initialized successfully (Direct API)")
        return True
    except Exception as e:
        print(f"⚠️ Direct initialization failed: {e}")
        try:
            # Fallback to standard initialization
            from groq import Groq
            groq_ai = Groq(api_key=GROQ_API_KEY)
            grok_mode = Groq(api_key=GROQ_API_KEY)
            print("✅ Groq clients initialized (Standard API)")
            return True
        except Exception as e2:
            print(f"❌ All initialization methods failed: {e2}")
            groq_ai = None
            grok_mode = None
            return False

# Initialize clients at startup
initialize_grok_clients()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/scrape")
async def scrape(request: Request):
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        print(f"🔍 Scraping URL: {url}, Mode: {mode}")
        data = scraper.scrape_website(url, mode)
        print(f"✅ Scraping completed for: {url}")
        
        if "error" in data: 
            return {"success": False, "error": data["error"]}
        
        # Add session_id for frontend compatibility
        data["session_id"] = data.get("scrape_id", str(uuid.uuid4()))
        return {"success": True, "data": data}
    
    except Exception as e:
        print(f"❌ Scraping error: {str(e)}")
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

@app.post("/groq-chat")
async def chat(request: Request):
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    if not message or not scraped:
        return {"success": False, "error": "Missing data"}
    if not groq_ai:
        return {"success": False, "error": "Groq AI client not initialized"}

    data = json.loads(scraped)
    system_prompt = """
You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
5. For greetings, respond naturally but briefly.
"""
    context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:8000]}\n\nQUESTION:\n{message}"

    try:
        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0,
            max_tokens=1500
        )
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No answer returned").strip()
        return {"success": True, "response": answer}
    except Exception as e:
        return {"success": False, "error": f"Groq API error: {str(e)}"}

@app.post("/export")
async def export(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

    filename = f"scraped_data"

    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }

    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}

    # Call the export function
    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))

# ========== GROK MODE - ENHANCED AI ==========
@app.post("/grok-mode")
async def grok_mode_endpoint(request: Request):
    """
    Grok Mode - Enhanced AI with deep reasoning for analyzing scraped data
    """
    try:
        form = await request.form()
        message = form.get("message")
        scraped = form.get("scraped_data")
        analysis_type = form.get("analysis_type", "comprehensive")
        
        if not message or not scraped:
            return {"success": False, "error": "Missing message or scraped data"}
        if not groq_mode:
            return {"success": False, "error": "Grok Mode client not initialized"}
        
        try:
            data = json.loads(scraped)
        except:
            return {"success": False, "error": "Invalid scraped data format"}
        
        # Grok Mode - Universal Questions Only (no scraped data)
        system_prompt = f"""You are Grok Mode - an advanced AI assistant for universal questions.

Rules:
1. ONLY answer universal/general knowledge questions
2. DO NOT use scraped data - ignore any website content provided
3. Use your comprehensive knowledge for all answers
4. Be helpful, detailed, and comprehensive
5. Analysis Type: {analysis_type}

Provide expert answers on any topic using your knowledge base. The scraped data is irrelevant - focus on universal knowledge."""
        
        # Build context - NO scraped data for universal questions only
        full_context = f"USER QUESTION:\n{message}\n\n(Note: This is a universal knowledge question. Provide comprehensive answer using your knowledge base.)"

        try:
            messages_to_send = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}  # Removed character limit completely for unlimited answers
            ]
            
            response = grok_mode.chat_completions_create(
                model=MODEL_DEEP,
                messages=messages_to_send,
                temperature=0.4,
                max_tokens=8000  # Increased from 2000 to 8000 for much longer answers
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", None)
            if not answer:
                answer = "No response generated from Grok Mode."
            
            return {
                "success": True, 
                "response": answer.strip(),
                "mode": "grok_mode",
                "model": MODEL_DEEP,
                "analysis_type": analysis_type
            }
            
        except Exception as e:
            print("🔥 Grok Mode Exception:", e)
            return {"success": False, "error": f"Grok Mode error: {str(e)}"}
    
    except Exception as e:
        print("🔥 Grok Mode General Exception:", e)
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}

# ========== GROK MODE SUMMARY ==========
@app.post("/grok-summary")
async def grok_summary(request: Request):
    """
    Quick summary using Grok Mode - extracts key facts instantly
    """
    form = await request.form()
    scraped = form.get("scraped_data")
    
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    if not groq_ai:
        return {"success": False, "error": "Groq AI client not initialized"}
    
    data = json.loads(scraped)
    
    system_prompt = """You are GROK MODE SUMMARY - Extract key facts instantly and accurately.

Provide a structured summary with:
1. MAIN TOPIC - What the page is about
2. KEY POINTS - 3-5 most important facts
3. STATISTICS - Any numbers/data found
4. CONCLUSION - Main takeaway

Only use data from the page. If info missing, say "Not found"."""
    
    context_parts = [f"URL: {data.get('url', '')}"]
    if data.get('title'):
        context_parts.append(f"Title: {data['title']}")
    if data.get('description'):
        context_parts.append(f"Description: {data['description']}")
    if data.get('paragraphs'):
        context_parts.append("\nContent:\n" + "\n".join(data['paragraphs'][:15]))
    
    try:
        response = groq_ai.chat_completions_create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(context_parts)}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")
        
        return {
            "success": True,
            "summary": answer.strip(),
            "mode": "grok_summary"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Summary error: {str(e)}"}
