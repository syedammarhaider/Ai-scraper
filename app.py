from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, json, time, uuid
import requests

from scraper import UltraScraper

load_dotenv()

app = FastAPI()

# CORS enable - browser block nahi karega
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Har error pe JSON return karo (HTML kabhi nahi)
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc)}
    )

# Max POST size 20MB tak allow karo
MAX_BODY = 20 * 1024 * 1024

@app.middleware("http")
async def size_limit(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        cl = request.headers.get("content-length")
        if cl and int(cl) > MAX_BODY:
            return JSONResponse(
                status_code=413,
                content={"success": False, "error": "Data bohot bara hai (20MB se zyada)"}
            )
    return await call_next(request)

# Groq setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

class GroqClient:
    def __init__(self, key):
        self.key = key
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def chat(self, model, messages, temperature=0, max_tokens=1500):
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        r = requests.post(self.url, headers=self.headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()

groq_ai = GroqClient(GROQ_API_KEY) if GROQ_API_KEY else None
grok_client = GroqClient(GROQ_API_KEY) if GROQ_API_KEY else None

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
        return {"success": False, "error": "URL daalein"}

    if not url.startswith("http"):
        url = "https://" + url

    print(f"Scraping: {url} ({mode})")

    try:
        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        data["session_id"] = str(uuid.uuid4())
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/groq-chat")
async def groq_chat(request: Request):
    if not groq_ai:
        return {"success": False, "error": "Groq ready nahi"}

    form = await request.form()
    message = form.get("message")
    scraped_str = form.get("scraped_data")

    if not message or not scraped_str:
        return {"success": False, "error": "Data missing"}

    try:
        data = json.loads(scraped_str)
    except:
        return {"success": False, "error": "Invalid data"}

    # Limit for Groq
    limited = {
        "title": data.get("title", ""),
        "url": data.get("url", ""),
        "paragraphs": data.get("paragraphs", [])[:80]
    }

    prompt = f"""SCRAPED DATA (summary):
{json.dumps(limited, indent=2)}

Sawal: {message}

Sirf is data se jawab do. Agar nahi mila to keh do "Is scraped data mein yeh information nahi hai." """

    try:
        resp = groq_ai.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500
        )
        answer = resp["choices"][0]["message"]["content"].strip()
        return {"success": True, "response": answer}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not grok_client:
        return {"success": False, "error": "Grok ready nahi"}

    form = await request.form()
    message = form.get("message")

    if not message:
        return {"success": False, "error": "Sawal daalein"}

    prompt = f"""Tum Grok ho - universal AI.
Sawal: {message}

Apne poore knowledge se jawab do - scraped data ignore karo."""

    try:
        resp = grok_client.chat(
            model=MODEL_DEEP,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=8000
        )
        answer = resp["choices"][0]["message"]["content"].strip()
        return {"success": True, "response": answer}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Export route (same as before)
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
        return {"success": False, "error": f"Format nahi mila: {fmt}"}

    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))