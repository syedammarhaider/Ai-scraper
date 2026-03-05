# app.py - AI Web Scraper with Groq + Flexible Analysis (2025 edition)
# Extended version - more robust, better prompt, larger token support, better exports

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import os
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# ────────────────────────────────────────────────
#               Logging Configuration
# ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ai-scraper")

# ────────────────────────────────────────────────
#               Load environment
# ────────────────────────────────────────────────

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not found in environment variables!")

# ────────────────────────────────────────────────
#               FastAPI App Setup
# ────────────────────────────────────────────────

app = FastAPI(
    title="AI Scraper - Ammar Edition",
    description="Web scraper + Groq-powered analysis",
    version="4.1.0"
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

# ────────────────────────────────────────────────
#               Groq Client
# ────────────────────────────────────────────────

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")

MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS_CHAT = 8192
MAX_TOKENS_GROK = 16384

# ────────────────────────────────────────────────
#               In-memory session storage
#               (for demo - use redis in production)
# ────────────────────────────────────────────────

sessions: Dict[str, Dict[str, Any]] = {}

# ────────────────────────────────────────────────
#               Routes
# ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "version": "4.1.0",
            "build_time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "groq_available": client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }


class ScrapeRequest(BaseModel):
    url: str
    mode: str = "comprehensive"
    javascript: bool = False
    max_pages: int = 60
    max_depth: int = 4


@app.post("/api/scrape")
async def api_scrape(req: ScrapeRequest):
    if not req.url:
        raise HTTPException(400, detail="URL is required")

    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    session_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        from scraper import UltraScraper  # late import to avoid circular issues

        scraper = UltraScraper()
        if req.javascript:
            logger.info(f"Enabling JS rendering for {url}")
            # In real production → use playwright or similar
            # Here we just log (your current scraper doesn't support JS yet)

        if req.mode == "crawl":
            data = scraper.crawl_website(
                url,
                mode="comprehensive",
                max_pages=req.max_pages,
                max_depth=req.max_depth
            )
        else:
            data = scraper.scrape_single_page(url, mode=req.mode)

        duration = round(time.time() - start_time, 2)

        sessions[session_id] = {
            "data": data,
            "url": url,
            "mode": req.mode,
            "created": datetime.utcnow().isoformat(),
            "duration": duration
        }

        return {
            "success": True,
            "session_id": session_id,
            "data": data,  # Return full data for frontend compatibility
            "data_preview": {
                "type": "crawl" if "pages" in data else "single",
                "page_count": len(data.get("pages", [])) if "pages" in data else 1,
                "duration_sec": duration
            }
        }

    except Exception as e:
        logger.exception("Scrape failed")
        raise HTTPException(500, detail=str(e))


@app.post("/api/chat")
async def chat_with_data(request: Request):
    if not client:
        raise HTTPException(503, "Groq API not available")

    form = await request.form()
    session_id = form.get("session_id")
    question = form.get("message")

    if not session_id or session_id not in sessions:
        raise HTTPException(400, "Invalid or expired session")

    if not question:
        raise HTTPException(400, "Message is required")

    scraped_data = sessions[session_id]["data"]

    # ────────────────────────────────────────────────
    #             IMPROVED SYSTEM PROMPT
    # ────────────────────────────────────────────────

    system_prompt = """You are a precise, obedient data analyst working EXCLUSIVELY with the provided scraped website data.

Core rules - you MUST follow these:
1. Use ONLY information present in the SCRAPED DATA shown below
2. Strictly follow the user's exact instruction regarding:
   • presentation style (list, table, json, markdown, bullet points…)
   • field renaming
   • filtering (only items containing X, only images with alt…)
   • sorting / grouping
   • counting
   • format conversion (json → text table, flat list…)
   • extraction of specific parts
3. When user asks for ALL / EVERY / COMPLETE / FULL:
   • include every internal link
   • include every external link
   • include every image
   • do NOT truncate unless physically impossible
4. If the requested information truly does NOT exist anywhere → respond ONLY with:
   "This information is not available in the scraped website data."
5. Never add external facts, opinions, explanations or invented data
6. Never refuse reasonable reformatting, counting, filtering or listing requests
7. Be as complete and literal as possible when user asks for full data
8. Start your answer directly with the requested output (no preamble unless asked)

Current date: {current_date}
""".format(current_date=datetime.now().strftime("%Y-%m-%d"))

    # ────────────────────────────────────────────────
    #             Build context (less truncation)
    # ────────────────────────────────────────────────

    context_lines = ["═" * 60]
    context_lines.append("SCRAPED DATA (untruncated where possible)")
    context_lines.append(f"Session: {session_id}")
    context_lines.append(f"Original URL: {sessions[session_id]['url']}")
    context_lines.append(f"Mode: {sessions[session_id]['mode']}")
    context_lines.append(f"Created: {sessions[session_id]['created']}")
    context_lines.append("═" * 60 + "\n")

    if "pages" in scraped_data:
        context_lines.append(f"Website crawl - {len(scraped_data['pages'])} pages")
        for i, page in enumerate(scraped_data["pages"], 1):
            context_lines.append(f"\nPAGE #{i}  ━━━━━━━━━━━━━━━━━━━━━━━")
            context_lines.append(f"URL:       {page.get('url','')}")
            context_lines.append(f"Title:     {page.get('title','')}")
            if page.get("description"):
                context_lines.append(f"Meta desc: {page['description'][:180]}")

            # Links - no heavy truncation
            int_links = page.get("internal_links", [])
            ext_links = page.get("external_links", [])
            if int_links:
                context_lines.append(f"Internal links ({len(int_links)}):")
                for lnk in int_links[:80]:  # soft limit - still generous
                    context_lines.append(f"  • {lnk.get('text','').strip()[:60]} → {lnk.get('url','')}")
                if len(int_links) > 80:
                    context_lines.append(f"  … + {len(int_links)-80} more internal links")

            if ext_links:
                context_lines.append(f"External links ({len(ext_links)}):")
                for lnk in ext_links[:80]:
                    context_lines.append(f"  • {lnk.get('text','').strip()[:60]} → {lnk.get('url','')}")
                if len(ext_links) > 80:
                    context_lines.append(f"  … + {len(ext_links)-80} more external links")

            imgs = page.get("images", [])
            if imgs:
                context_lines.append(f"Images ({len(imgs)}):")
                for img in imgs[:30]:
                    context_lines.append(f"  • {img.get('alt','no alt')[:50]} → {img.get('url','')}")
    else:
        # single page
        context_lines.append("SINGLE PAGE DATA")
        for k, v in scraped_data.items():
            if isinstance(v, (list, dict)):
                context_lines.append(f"{k}: ({len(v)} items)")
            else:
                context_lines.append(f"{k}: {str(v)[:180]}")

    context_lines.append("\nUSER INSTRUCTION:")
    context_lines.append(question)
    context = "\n".join(context_lines)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": context}
            ],
            temperature=0.0,
            max_tokens=MAX_TOKENS_CHAT,
            top_p=1.0
        )

        answer = response.choices[0].message.content.strip()

        return JSONResponse({
            "success": True,
            "response": answer,
            "tokens_used": response.usage.total_tokens if response.usage else None
        })

    except Exception as e:
        logger.exception("Groq chat failed")
        raise HTTPException(500, detail=f"Groq error: {str(e)}")


# ────────────────────────────────────────────────
#               Export endpoint (enhanced)
# ────────────────────────────────────────────────

@app.get("/api/export/{session_id}/{format}")
async def export_data(session_id: str, format: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")

    data = sessions[session_id]["data"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"scrape_export_{timestamp}"

    from scraper import UltraScraper
    scraper = UltraScraper()

    handlers = {
        "json":     (scraper.save_as_json,    "application/json",        ".json"),
        "csv":      (scraper.save_as_csv,     "text/csv",                ".csv"),
        "xlsx":     (scraper.save_as_excel,   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        "txt":      (scraper.save_as_text,    "text/plain",              ".txt"),
        "pdf":      (scraper.save_as_pdf,     "application/pdf",         ".pdf"),
        "md":       (lambda d,f: (scraper.save_as_markdown(d,f), "text/markdown", ".md")),
    }

    if format not in handlers:
        raise HTTPException(400, f"Unsupported format. Allowed: {', '.join(handlers.keys())}")

    handler, mime, ext = handlers[format]
    path = handler(data, filename + ext.replace(".", "_temp"))

    if not path or not os.path.exists(path):
        raise HTTPException(500, "Failed to generate export file")

    return FileResponse(
        path,
        media_type=mime,
        filename=f"{filename}{ext}"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )