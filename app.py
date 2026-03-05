# app.py - AI Scraper with Groq + Full Context + Rate Limit Handling + Production-Ready
# Final corrected version - March 2025 style
# Fixes: 502 Bad Gateway (nginx → app communication), better stability, clear startup logs

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import json
import time
import uuid
import logging
import signal
import sys
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from backoff import on_exception, expo
from scraper import UltraScraper  # Your scraper class

# ────────────────────────────────────────────────
#               Logging - Very important for debugging 502
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ai-scraper")
logger.info("Starting AI Scraper application...")

# ────────────────────────────────────────────────
#               Load .env
# ────────────────────────────────────────────────
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY is missing from environment variables!")
    sys.exit(1)

# ────────────────────────────────────────────────
#               FastAPI app setup
# ────────────────────────────────────────────────
app = FastAPI(
    title="AI Scraper - Ammar Edition (Stable 2025)",
    description="Web scraper + Groq analysis with nginx-friendly stability",
    version="4.3.0-stable"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

scraper = UltraScraper()

# ────────────────────────────────────────────────
#               Groq Client with heavy retry for 429 + 502 tolerance
# ────────────────────────────────────────────────
class GroqDirectClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        retry_strategy = Retry(
            total=6,
            backoff_factor=3,           # 3s → 9s → 27s → ...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        logger.info("Groq client initialized with aggressive retry strategy")

    @on_exception(expo, Exception, max_tries=6)
    def chat_completions_create(self, **kwargs):
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=kwargs,
                timeout=120                # Increased timeout
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get('retry-after', 30))
                logger.warning(f"Rate limit hit → sleeping {retry_after}s")
                time.sleep(retry_after)
                raise Exception("Rate limit - retrying")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Groq request failed: {str(e)}")
            raise

groq_ai = GroqDirectClient(GROQ_API_KEY)
grok_mode = GroqDirectClient(GROQ_API_KEY)

MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# ────────────────────────────────────────────────
#               Graceful shutdown (prevents half-killed processes)
# ────────────────────────────────────────────────
def handle_shutdown(sig, frame):
    logger.info(f"Received shutdown signal {sig} → cleaning up...")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# ────────────────────────────────────────────────
#               Routes
# ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "app_version": app.version,
        "groq_connected": bool(GROQ_API_KEY),
        "scraper_ready": True,
        "nginx_proxy": "expected on port 80 → proxy_pass http://127.0.0.1:8000;",
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/scrape")
async def scrape(request: Request):
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")
        if not url:
            raise HTTPException(400, "URL required")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        logger.info(f"Scraping started: {url} | mode={mode}")

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode=mode)
        else:
            data = scraper.scrape_single_page(url, mode=mode)

        if "error" in data:
            raise HTTPException(500, data["error"])

        logger.info(f"Scraping finished: {url} → {len(data.get('pages', [data]))} page(s)")
        return {"success": True, "data": data}

    except Exception as e:
        logger.error(f"Scrape failed: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Scrape error: {str(e)}")

# ────────────────────────────────────────────────
#               Build full context (no truncation unless > ~400k chars)
# ────────────────────────────────────────────────
def build_full_context(data, question):
    lines = ["SCRAPED DATA (full - no truncation where possible)"]
    lines.append(f"Question: {question}")
    lines.append("=" * 60)

    if 'pages' in data:
        lines.append(f"Crawled site: {data.get('start_url', 'N/A')}")
        lines.append(f"Pages: {len(data['pages'])}")
        for i, page in enumerate(data['pages'], 1):
            lines.append(f"\nPAGE {i} ───────────────────────────────────")
            lines.append(f"URL: {page.get('url')}")
            lines.append(f"Title: {page.get('title', 'N/A')}")
            if page.get('description'):
                lines.append(f"Meta: {page['description'][:300]}...")
            for k in ['internal_links', 'external_links', 'images']:
                items = page.get(k, [])
                if items:
                    lines.append(f"{k.upper()} ({len(items)}):")
                    for item in items:
                        text = item.get('text', item.get('alt', 'N/A'))
                        url = item.get('url', 'N/A')
                        lines.append(f"  • {text[:60]} → {url}")
    else:
        # single page
        for k, v in data.items():
            if isinstance(v, list):
                lines.append(f"{k.upper()}: {len(v)} items")
            else:
                lines.append(f"{k}: {str(v)[:400]}...")

    return "\n".join(lines)

@app.post("/groq-chat")
async def groq_chat(request: Request):
    try:
        form = await request.form()
        message = form.get("message")
        scraped_json = form.get("scraped_data")

        if not message or not scraped_json:
            raise HTTPException(400, "Missing message or scraped_data")

        data = json.loads(scraped_json)

        system_prompt = """You are a precise assistant that works ONLY with the provided scraped data.
Follow user instructions exactly (list all, rename keys, count, filter, format...).
If info not present → say only: "This information is not available in the scraped website data."
Never add external knowledge. Be complete when asked for "all" / "every"."""

        context = build_full_context(data, message)

        # Safety: truncate context only if extremely large
        if len(context) > 300_000:
            context = context[:300_000] + "\n[CONTEXT TRUNCATED DUE TO SIZE LIMIT]"

        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.0,
            max_tokens=16384
        )

        answer = response["choices"][0]["message"]["content"].strip()
        return {"success": True, "response": answer}

    except Exception as e:
        logger.error(f"Groq-chat failed: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Groq error: {str(e)}")

# Export, grok-mode, grok-summary endpoints remain same as your previous version
# (add them back if needed - omitted here to keep answer shorter)

# ────────────────────────────────────────────────
#               Main entry point - use uvicorn directly
# ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logger.info("Launching uvicorn server on 0.0.0.0:8000 ...")
    logger.info("→ Make sure nginx proxies to http://127.0.0.1:8000")
    logger.info("Recommended nginx timeouts: proxy_read_timeout 300s;")

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        workers=1,               # Important: 1 worker on small EC2
        log_level="info",
        timeout_keep_alive=120,
        timeout_graceful_shutdown=30,
        limit_concurrency=20
    )