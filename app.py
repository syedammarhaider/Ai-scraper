# ===========================
# FINAL PRODUCTION APP.PY
# Large Data Optimized + Exact Scraped Data QA
# ===========================

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

import os, json, uuid, gzip, re
import requests
from typing import Dict, Any

from scraper import UltraScraper

# ===========================
# INITIAL SETUP
# ===========================

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

app.mount("/static", StaticFiles(directory="static"), name="static")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

MAX_RESPONSE_SIZE = 50 * 1024 * 1024
MAX_PAGES_LARGE = 100

# ===========================
# GROQ DIRECT CLIENT
# ===========================

class GroqDirectClient:
    def __init__(self, api_key):
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat_completions_create(self, model, messages, temperature=0, max_tokens=2000):
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()

groq_ai = GroqDirectClient(GROQ_API_KEY)
grok_mode = GroqDirectClient(GROQ_API_KEY)

# ===========================
# COMPRESSION UTILS
# ===========================

def compress_data(data: str) -> str:
    return gzip.compress(data.encode()).hex()

def decompress_data(hex_data: str) -> str:
    try:
        return gzip.decompress(bytes.fromhex(hex_data)).decode()
    except:
        return hex_data

# ===========================
# DATA OPTIMIZATION
# ===========================

def optimize_data_size(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        size = len(json.dumps(data))
    except:
        return data

    if size > MAX_RESPONSE_SIZE:
        optimized = data.copy()

        if 'paragraphs' in optimized:
            optimized['paragraphs'] = optimized['paragraphs'][:50]
        if 'images' in optimized:
            optimized['images'] = optimized['images'][:20]
        if 'internal_links' in optimized:
            optimized['internal_links'] = optimized['internal_links'][:100]
        if 'external_links' in optimized:
            optimized['external_links'] = optimized['external_links'][:100]
        if 'pages' in optimized:
            optimized['pages'] = optimized['pages'][:10]
        if 'full_text' in optimized:
            optimized['full_text'] = optimized['full_text'][:50000]

        optimized["data_truncated"] = True
        return optimized

    return data

# ===========================
# HOME
# ===========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ===========================
# SCRAPE
# ===========================

@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")
    max_pages = int(form.get("max_pages", MAX_PAGES_LARGE))

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith("http"):
        url = "https://" + url

    if mode == "comprehensive":
        data = scraper.crawl_website(url, mode, max_pages=max_pages)
    else:
        data = scraper.scrape_single_page(url, mode)

    if "error" in data:
        return {"success": False, "error": data["error"]}

    optimized = optimize_data_size(data)
    optimized["session_id"] = str(uuid.uuid4())
    optimized["scrape_id"] = optimized.get("scrape_id", str(uuid.uuid4()))

    return {"success": True, "data": optimized}

# ============================================================
# EXACT SCRAPED DATA QA (ULTRA STRICT ANSWERING SYSTEM)
# ============================================================

def extract_number_from_question(question: str):
    """Extract number like '5 urls'"""
    match = re.search(r'\b(\d+)\b', question)
    return int(match.group(1)) if match else None

def build_exact_answer_from_data(question: str, data: Dict[str, Any]):
    """
    This function ensures:
    - If asking URLs → return ALL URLs
    - If asking images → return ALL image URLs
    - If asking N URLs → return exactly N
    - No AI guessing
    """

    q = question.lower()

    number_requested = extract_number_from_question(q)

    # ===========================
    # ALL URLS
    # ===========================

    if "url" in q or "link" in q:

        all_urls = []

        if data.get("internal_links"):
            all_urls.extend(data["internal_links"])

        if data.get("external_links"):
            all_urls.extend(data["external_links"])

        if data.get("pages"):
            for p in data["pages"]:
                if isinstance(p, dict) and p.get("url"):
                    all_urls.append(p["url"])

        all_urls = list(dict.fromkeys(all_urls))  # remove duplicates

        if number_requested:
            all_urls = all_urls[:number_requested]

        if not all_urls:
            return "No URLs found in scraped data."

        return "\n".join(all_urls)

    # ===========================
    # IMAGE URLS
    # ===========================

    if "image" in q:

        images = data.get("images", [])

        if number_requested:
            images = images[:number_requested]

        if not images:
            return "No image URLs found in scraped data."

        return "\n".join(images)

    # ===========================
    # PARAGRAPHS
    # ===========================

    if "paragraph" in q:

        paragraphs = data.get("paragraphs", [])

        if number_requested:
            paragraphs = paragraphs[:number_requested]

        if not paragraphs:
            return "No paragraphs found."

        return "\n\n".join(paragraphs)

    # ===========================
    # TITLE
    # ===========================

    if "title" in q:
        return data.get("title", "Title not found.")

    # ===========================
    # DESCRIPTION
    # ===========================

    if "description" in q:
        return data.get("description", "Description not found.")

    # ===========================
    # FULL TEXT
    # ===========================

    if "full text" in q:
        return data.get("full_text", "Full text not available.")

    return None  # fallback to AI


# ===========================
# GROQ CHAT (UPDATED)
# ===========================

@app.post("/groq-chat")
async def chat(request: Request):

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing data"}

    try:
        data = json.loads(scraped)

        if data.get("is_compressed"):
            decompressed = decompress_data(data["compressed_data"])
            data = json.loads(decompressed)

    except:
        return {"success": False, "error": "Invalid scraped data"}

    # ============================================================
    # FIRST: TRY EXACT EXTRACTION (NO AI USED)
    # ============================================================

    exact_answer = build_exact_answer_from_data(message, data)

    if exact_answer:
        return {"success": True, "response": exact_answer}

    # ============================================================
    # FALLBACK: STRICT AI FROM SCRAPED DATA ONLY
    # ============================================================

    system_prompt = """
You are an EXACT factual AI assistant.

Rules:
1. ONLY use provided scraped data.
2. If answer not present, say:
   "This information is not available in the scraped website data."
3. Do NOT summarize unless asked.
4. If question asks for ALL items, return ALL.
5. If question asks for specific number (e.g., 5 URLs), return exactly that count.
6. Never guess.
"""

    context = f"""
SCRAPED DATA:
{json.dumps(data, indent=2, ensure_ascii=False)}

QUESTION:
{message}
"""

    response = groq_ai.chat_completions_create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context}
        ],
        temperature=0,
        max_tokens=4000
    )

    answer = response["choices"][0]["message"]["content"]

    return {"success": True, "response": answer.strip()}

# ===========================
# EXPORT (UNCHANGED)
# ===========================

@app.post("/export")
async def export(request: Request):

    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

    if isinstance(data, dict) and data.get("is_compressed"):
        decompressed = decompress_data(data["compressed_data"])
        data = json.loads(decompressed)

    filename = "scraped_data"

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

# ===========================
# GLOBAL ERROR HANDLER
# ===========================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )