from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from scraper import UltraScraper
import os
import json
import time
import requests

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ────────────────────────────────────────────────
scraper = UltraScraper()

# ────────────────────────────────────────────────
class GeminiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    def generate(self, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            }
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }
        r = requests.post(self.url, headers=headers, json=payload, timeout=70)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
gemini_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = GeminiClient(GEMINI_API_KEY)
        print("Gemini client initialized (model = gemini-2.0-flash)")
    except Exception as e:
        print("Gemini init failed →", e)

# ────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "gemini": "connected" if gemini_client else "not connected",
        "model": "gemini-2.0-flash"
    }


@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url", "").strip()
    mode = form.get("mode", "comprehensive")

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        if mode == "single":
            data = scraper.scrape_single_page(url)
        else:
            data = scraper.crawl_website(url, mode=mode, max_pages=40, max_depth=4)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        return {"success": True, "data": data}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/groq-chat")
async def chat_with_scraped_data(request: Request):
    if not gemini_client:
        return {"success": False, "error": "Gemini API key missing or invalid"}

    form = await request.form()
    message = form.get("message", "").strip()
    scraped_json = form.get("scraped_data", "")

    if not message or not scraped_json:
        return {"success": False, "error": "message and scraped_data required"}

    try:
        data = json.loads(scraped_json)
    except:
        return {"success": False, "error": "Invalid JSON in scraped_data"}

    context = build_very_small_context(data, message)

    try:
        prompt = f"""You are a helpful assistant that answers questions using ONLY the provided website data.
Never make up information. If the answer is not in the data → say "I don't have that information".

DATA:
{context}

QUESTION:
{message}

Answer concisely and directly:"""

        answer = gemini_client.generate(prompt)
        return {
            "success": True,
            "response": answer.strip(),
            "model": "gemini-2.0-flash"
        }

    except Exception as e:
        return {"success": False, "error": f"Gemini → {str(e)}"}


def build_very_small_context(data: dict, question: str) -> str:
    lines = ["[Website data — first page only]"]

    wants_edit = any(w in question.lower() for w in [
        'change', 'modify', 'edit', 'update', 'rewrite', 'replace', 'remove', 'add'
    ])

    # ── Single page ───────────────────────────────
    if 'url' in data and 'title' in data:
        lines.append(f"Page title: {data.get('title','')[:140]}")
        if d := data.get('description',''):
            lines.append(f"Meta description: {d[:120]}")

        if h1 := data.get('headings',{}).get('h1',[]):
            lines.append(f"H1: {h1[0][:140] if h1 else ''}")

        if paras := data.get('paragraphs', []):
            limit = 3 if not wants_edit else 5
            short_paras = [p for p in paras[:limit] if 40 <= len(p) <= 320]
            if short_paras:
                lines.append("Main content excerpts:")
                for p in short_paras:
                    lines.append(f"• {p}")

    # ── Crawled site (only first page!) ───────────
    elif 'pages' in data and data['pages']:
        page = data['pages'][0]   # <--- very important: only first page
        lines.append(f"Website: {data.get('start_url','')}")
        lines.append(f"Page 1 / {len(data['pages'])} → {page.get('title','')[:140]}")

        if d := page.get('description',''):
            lines.append(f"Description: {d[:110]}")

        if h1 := page.get('headings',{}).get('h1',[]):
            lines.append(f"H1: {h1[0][:140] if h1 else ''}")

        if paras := page.get('paragraphs', []):
            limit = 3 if not wants_edit else 6
            short_paras = [p for p in paras[:limit] if 40 <= len(p) <= 300]
            if short_paras:
                lines.append("Content snippets:")
                for p in short_paras:
                    lines.append(f"• {p}")

    lines.append(f"\nUser question: {question}")
    return "\n".join(lines)


@app.post("/grok-mode")
async def universal_chat(request: Request):
    if not gemini_client:
        return {"success": False, "error": "Gemini not available"}

    form = await request.form()
    message = form.get("message", "").strip()

    if not message:
        return {"success": False, "error": "message required"}

    try:
        prompt = f"You are a knowledgeable and direct assistant.\n\nUser: {message}\n\nAnswer clearly and helpfully:"
        answer = gemini_client.generate(prompt)
        return {
            "success": True,
            "response": answer.strip(),
            "mode": "gemini-2.0-flash"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/export")
async def export_data(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "format and data required"}

    filename = f"scraped_{int(time.time())}"
    handlers = {
        "json":  scraper.save_as_json,
        "csv":   scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt":   scraper.save_as_text,
        "pdf":   scraper.save_as_pdf,
    }

    if fmt not in handlers:
        return {"success": False, "error": f"format {fmt!r} not supported"}

    try:
        path = handlers[fmt](data, filename)
        if not path:
            return {"success": False, "error": "Could not create file"}
        return FileResponse(path, filename=os.path.basename(path))
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)