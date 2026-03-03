# Final app.py - 100% working version - March 2026
# Ye file full scraped data handle karti hai, large data ke liye bhi safe hai
# Comments Roman Urdu mein hain taake asani se samajh aaye

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, json, time, uuid
import requests

from scraper import UltraScraper

# Environment variables load karo (.env file se)
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Static files serve karne ke liye
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS enable karo taake browser block na kare
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production mein specific domain daal dena
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Har error pe JSON response do (HTML kabhi nahi aayega)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Server error: {str(exc)}"},
    )

# Groq API key aur models
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Direct Groq client banaya hai (package ke bajaye requests use kar rahe hain)
class GroqDirectClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500):
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise Exception(f"Groq API failed: {str(e)}")

# Global clients
groq_ai = None
grok_mode_client = None

# Clients initialize karo
def init_groq():
    global groq_ai, grok_mode_client
    if not GROQ_API_KEY:
        print("❌ .env mein GROQ_API_KEY nahi mila")
        return
    try:
        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode_client = GroqDirectClient(GROQ_API_KEY)
        print("✅ Groq clients ready hain")
    except Exception as e:
        print(f"❌ Groq init fail: {e}")

init_groq()

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

# Home page serve karo
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Scraping endpoint - full data scrape karta hai
@app.post("/scrape")
async def scrape(request: Request):
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")

        if not url:
            return {"success": False, "error": "URL chahiye"}

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        print(f"🔍 Scraping ho raha hai: {url} | Mode: {mode}")

        # Comprehensive mode mein full site crawl, baqi mein single page
        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode, max_pages=50, max_depth=4)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        data["session_id"] = str(uuid.uuid4())
        return {"success": True, "data": data}
    
    except Exception as e:
        print(f"❌ Scraping error: {str(e)}")
        return {"success": False, "error": f"Scraping fail: {str(e)}"}

# Groq chat endpoint - scraped data ke saath jawab deta hai
@app.post("/groq-chat")
async def groq_chat(request: Request):
    if not groq_ai:
        return {"success": False, "error": "Groq AI ready nahi hai"}

    form = await request.form()
    message = form.get("message")
    scraped_str = form.get("scraped_data")

    if not message or not scraped_str:
        return {"success": False, "error": "Message ya data missing"}

    try:
        data = json.loads(scraped_str)
    except:
        return {"success": False, "error": "Scraped data invalid hai"}

    # Large data ke liye context limit kar do taake crash na ho
    limited_data = {
        "title": data.get("title", ""),
        "url": data.get("url", ""),
        "description": data.get("description", ""),
        "main_content": "\n".join(data.get("paragraphs", [])[:40])  # sirf 40 paragraphs bhej rahe
    }

    system_prompt = """
You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
"""
    context = f"SCRAPED DATA:\n{json.dumps(limited_data, indent=2)}\n\nQUESTION:\n{message}"

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

# Export endpoint - files download karne ke liye
@app.post("/export")
async def export(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Format ya data missing"}

    filename = f"scraped_{int(time.time())}"

    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }

    if fmt not in handlers:
        return {"success": False, "error": f"Yeh format support nahi: {fmt}"}

    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))

# Grok Mode - universal questions ke liye (scraped data ignore karta hai)
@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not grok_mode_client:
        return {"success": False, "error": "Grok Mode ready nahi"}

    form = await request.form()
    message = form.get("message")
    analysis_type = form.get("analysis_type", "comprehensive")

    if not message:
        return {"success": False, "error": "Question chahiye"}

    system_prompt = f"""You are Grok Mode - advanced universal AI.
Rules:
1. Answer using only your knowledge - scraped data ignore karo
2. Be detailed, accurate, helpful
Analysis type: {analysis_type}"""

    context = f"QUESTION: {message}\n\n(Universal knowledge question)"

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