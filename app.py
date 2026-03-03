# Final working app.py - March 2025 version
# All routes consistent, CORS enabled, JSON error responses only
# Groq endpoints fixed, function names match frontend calls

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, json, time, uuid
import requests

from scraper import UltraScraper

# Load environment variables
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Enable CORS - this fixes most "<!DOCTYPE html>" issues from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                # Change to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Force JSON response even on crashes (no more HTML error pages)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Server error: {str(exc)}"},
    )

# GROQ API Key & Models
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Direct Groq client (more reliable than old groq package)
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
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=45
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise Exception(f"Groq API failed: {str(e)}")

# Global Groq clients
groq_ai = None
grok_mode_client = None

def init_groq_clients():
    global groq_ai, grok_mode_client
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY missing in .env")
        return False
    try:
        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode_client = GroqDirectClient(GROQ_API_KEY)
        print("✅ Groq clients initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Groq init failed: {e}")
        return False

init_groq_clients()

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    print(f"Scraping: {url} | Mode: {mode}")

    if mode == "comprehensive":
        data = scraper.crawl_website(url, mode, max_pages=50, max_depth=4)
    else:
        data = scraper.scrape_single_page(url, mode)

    if "error" in data:
        return {"success": False, "error": data["error"]}

    data["session_id"] = str(uuid.uuid4())
    return {"success": True, "data": data}

@app.post("/groq-chat")
async def groq_chat(request: Request):
    if not groq_ai:
        return {"success": False, "error": "Groq AI not initialized"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing message or scraped_data"}

    try:
        data = json.loads(scraped)
    except:
        return {"success": False, "error": "Invalid scraped_data JSON"}

    system_prompt = """
You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
"""
    context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:12000]}\n\nQUESTION:\n{message}"

    try:
        resp = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0,
            max_tokens=1500
        )
        answer = resp["choices"][0]["message"]["content"].strip()
        return {"success": True, "response": answer}
    except Exception as e:
        return {"success": False, "error": f"Groq error: {str(e)}"}

@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not grok_mode_client:
        return {"success": False, "error": "Grok Mode not initialized"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    analysis_type = form.get("analysis_type", "comprehensive")

    if not message or not scraped:
        return {"success": False, "error": "Missing message or scraped_data"}

    try:
        json.loads(scraped)  # just validate
    except:
        return {"success": False, "error": "Invalid scraped_data"}

    system_prompt = f"""You are Grok Mode - advanced universal AI.
Rules:
1. Answer using only your knowledge - DO NOT use scraped data
2. Be detailed, accurate, helpful
Analysis type: {analysis_type}"""

    context = f"QUESTION: {message}\n\n(Universal knowledge question - ignore any website data)"

    try:
        resp = grok_mode_client.chat_completions_create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.4,
            max_tokens=8000
        )
        answer = resp["choices"][0]["message"]["content"].strip()
        return {"success": True, "response": answer}
    except Exception as e:
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}

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