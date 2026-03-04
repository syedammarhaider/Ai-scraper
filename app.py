# ============================================================
# FINAL PRODUCTION APP.PY
# Ultra-Professional Scraped Data AI Analysis Engine
# ============================================================

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from typing import Dict, Any
import os
import json
import time
import uuid
import gzip
import logging
import random
import requests

from scraper import UltraScraper

# ============================================================
# INITIALIZATION
# ============================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()
app.mount("/static", StaticFiles(directory="static"), name="static")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

MAX_RESPONSE_SIZE = 50 * 1024 * 1024
MAX_PAGES_LARGE = 100

# ============================================================
# SAFE DATA HANDLING
# ============================================================

def compress_data(data: str) -> str:
    return gzip.compress(data.encode("utf-8")).hex()

def decompress_data_safe(hex_data: str) -> str:
    try:
        raw = bytes.fromhex(hex_data)
        return gzip.decompress(raw).decode("utf-8")
    except Exception:
        return hex_data

def safe_json_loads(data: Any) -> Any:
    if isinstance(data, dict):
        return data
    if not isinstance(data, str):
        return {}
    try:
        return json.loads(data)
    except Exception:
        return {}

# ============================================================
# GROQ DIRECT CLIENT (Rate-limit Safe)
# ============================================================

class GroqDirectClient:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat(self, model: str, messages, temperature=0, max_tokens=4096):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        retries = 3
        base_delay = 1

        for attempt in range(retries):
            try:
                response = requests.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 429:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logging.warning(f"Rate limit hit. Retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                result = response.json()

                if "choices" not in result:
                    raise Exception("Invalid API response format")

                return result["choices"][0]["message"]["content"].strip()

            except Exception as e:
                logging.error(f"Groq API error: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(base_delay)

        raise Exception("Groq request failed after retries")

groq_ai = GroqDirectClient(GROQ_API_KEY) if GROQ_API_KEY else None

# ============================================================
# OPTIMIZE DATA SIZE
# ============================================================

def optimize_data_size(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data_str = json.dumps(data, ensure_ascii=False)
        if len(data_str) > MAX_RESPONSE_SIZE:
            return {
                "compressed_data": compress_data(data_str),
                "is_compressed": True
            }
        return data
    except Exception:
        return data

# ============================================================
# ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "healthy"}

# ============================================================
# SCRAPE
# ============================================================

@app.post("/scrape")
async def scrape(request: Request):
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")
        max_pages = int(form.get("max_pages", MAX_PAGES_LARGE))

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        logging.info(f"Scraping {url}")

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode, max_pages=max_pages)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        optimized = optimize_data_size(data)
        optimized["session_id"] = str(uuid.uuid4())
        optimized["scrape_id"] = str(uuid.uuid4())

        return {"success": True, "data": optimized}

    except Exception as e:
        logging.error(f"Scrape error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================
# ULTRA PROFESSIONAL SCRAPED DATA AI
# ============================================================

@app.post("/groq-chat")
async def groq_chat(request: Request):
    try:
        form = await request.form()
        user_message = form.get("message")
        scraped_raw = form.get("scraped_data")

        if not user_message or not scraped_raw:
            return {"success": False, "error": "Missing message or scraped_data"}

        scraped_data = safe_json_loads(scraped_raw)

        if scraped_data.get("is_compressed"):
            decompressed = decompress_data_safe(scraped_data["compressed_data"])
            scraped_data = safe_json_loads(decompressed)

        context = json.dumps(scraped_data, ensure_ascii=False, indent=2)

        if len(context) > 30000:
            context = context[:30000] + "\n[DATA TRUNCATED FOR TOKEN LIMIT]"

        system_prompt = """
You are an Elite Institutional Data Intelligence System.

STRICT RULES:
1. You may ONLY use information present in the provided SCRAPED DATA.
2. Execute ANY transformation, filtering, sorting, restructuring, counting,
   comparison, extraction, grouping, or formatting command exactly as instructed.
3. If user asks for ALL data → return ALL.
4. If user specifies number N → return EXACTLY N.
5. Never guess. Never hallucinate.
6. If information does not exist, say:
   "This information is not present in the scraped website data."
7. Formatting must be executive-grade:
   - Use # headings
   - Structured lists
   - Tables when appropriate
   - Professional tone
   - No casual language
8. Be exhaustive and precise.
"""

        full_prompt = f"""
SCRAPED DATA:
{context}

USER INSTRUCTION:
{user_message}
"""

        if not groq_ai:
            return {
                "success": True,
                "response": "AI engine unavailable. Raw scraped data returned.",
                "data": scraped_data
            }

        answer = groq_ai.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0,
            max_tokens=4096
        )

        return {
            "success": True,
            "response": answer
        }

    except Exception as e:
        logging.error(f"AI error: {e}")
        return {
            "success": False,
            "error": "AI analysis failed."
        }

# ============================================================
# EXPORT
# ============================================================

@app.post("/export")
async def export(request: Request):
    try:
        body = await request.json()
        fmt = body.get("format")
        data = body.get("data")

        if not fmt or not data:
            return {"success": False, "error": "Missing  the format or data"}

        if isinstance(data, dict) and data.get("is_compressed"):
            decompressed = decompress_data_safe(data["compressed_data"])
            data = safe_json_loads(decompressed)

        filename = f"scraped_data_{int(time.time())}"

        handlers = {
            "json": scraper.save_as_json,
            "csv": scraper.save_as_csv,
            "excel": scraper.save_as_excel,
            "txt": scraper.save_as_text,
            "pdf": scraper.save_as_pdf
        }

        if fmt not in handlers:
            return {"success": False, "error": "Unsupported format"}

        path = handlers[fmt](data, filename)
        return FileResponse(path, filename=os.path.basename(path))

    except Exception as e:
        logging.error(f"Export error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )