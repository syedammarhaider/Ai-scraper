
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
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"

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
        print("Gemini client initialized (model = gemini-3-flash-preview)")
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
        "model": "gemini-3-flash-preview"
    }


@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url", "").strip()
    mode = form.get("mode", "comprehensive")
    use_pattern = form.get("use_pattern", "false").lower() == "true"

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        if use_pattern and gemini_client and mode != "single":
            print(f"Using AI Pattern Mode for: {url}")
            first_page = scraper.scrape_single_page(url, mode="comprehensive")
            if "error" in first_page:
                return {"success": False, "error": first_page["error"]}
            
            pattern_prompt = f"""Analyze this scraped page data and create a structured extraction pattern.
Return ONLY a JSON object with the field names and types to extract from similar pages.

Page URL: {url}
Page Title: {first_page.get('title', '')[:100]}
Description: {first_page.get('description', '')[:200]}
Headings: {first_page.get('headings', {})}
First paragraph: {first_page.get('paragraphs', [''])[0][:200] if first_page.get('paragraphs') else ''}

Return JSON like:
{{
    "title": "string - page title",
    "description": "string - meta description", 
    "price": "string - product price if found",
    "content": "string - main content/description",
    "images": "array - image URLs"
}}

Respond ONLY with JSON, no explanation."""

            try:
                pattern_response = gemini_client.generate(pattern_prompt)
                import re
                json_match = re.search(r'\{[\s\S]*\}', pattern_response)
                if json_match:
                    extraction_pattern = json.loads(json_match.group())
                else:
                    extraction_pattern = {"title": "string", "content": "string"}
            except Exception as pe:
                print(f"Pattern creation failed: {pe}")
                extraction_pattern = {"title": "string", "content": "string"}
            
            aggregate_data = scraper.crawl_website_with_pattern(url, mode=mode, max_pages=40, max_depth=4, pattern=extraction_pattern)
            aggregate_data["ai_pattern"] = extraction_pattern
            aggregate_data["pattern_mode"] = True
            
            return {"success": True, "data": aggregate_data, "pattern": extraction_pattern}
        else:
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
            "model": "gemini-3-flash-preview"
        }

    except Exception as e:
        return {"success": False, "error": f"Gemini → {str(e)}"}


def build_very_small_context(data: dict, question: str) -> str:
    """Build comprehensive context from scraped data - gives exact answers based on what's asked"""
    question_lower = question.lower()
    lines = []
    
    # Detect what user is asking for
    wants_urls = any(w in question_lower for w in ['url', 'links', 'addresses', 'site', 'websites'])
    wants_paragraphs = any(w in question_lower for w in ['paragraph', 'content', 'text', 'details', 'information', 'write', 'article'])
    wants_images = any(w in question_lower for w in ['image', 'photo', 'picture', 'img'])
    wants_headings = any(w in question_lower for w in ['heading', 'title', 'header'])
    wants_edit = any(w in question_lower for w in ['change', 'modify', 'edit', 'update', 'rewrite', 'replace', 'remove', 'add', 'convert'])
    wants_all = any(w in question_lower for w in ['all', 'everything', 'full', 'complete'])
    wants_more = any(w in question_lower for w in ['more', 'detailed', 'detail', 'explain'])
    
    # Single page data
    if 'url' in data and 'title' in data:
        lines.append("=== SCRAPED PAGE ===")
        lines.append(f"URL: {data.get('url', 'N/A')}")
        
        if wants_headings or wants_all or not any([wants_urls, wants_paragraphs, wants_images]):
            lines.append("--- HEADINGS ---")
            headings = data.get('headings', {})
            for level in ['h1', 'h2', 'h3']:
                if headings.get(level):
                    for h in headings[level][:10]:
                        lines.append(f"{level.upper()}: {h}")
        
        if wants_paragraphs or wants_all or wants_more:
            lines.append(f"--- PARAGRAPHS ({len(data.get('paragraphs', []))} total) ---")
            paras = data.get('paragraphs', [])
            for i, p in enumerate(paras, 1):
                lines.append(f"[Para {i}]: {p}")
        
        if wants_urls or wants_all:
            lines.append("--- ALL INTERNAL LINKS ---")
            for link in data.get('internal_links', [])[:50]:
                lines.append(f"• {link.get('url', 'N/A')}")
            lines.append("--- ALL EXTERNAL LINKS ---")
            for link in data.get('external_links', [])[:20]:
                lines.append(f"• {link.get('url', 'N/A')}")
        
        if wants_images or wants_all:
            lines.append("--- IMAGES ---")
            for img in data.get('images', [])[:20]:
                lines.append(f"URL: {img.get('url', 'N/A')}")
                if img.get('alt'):
                    lines.append(f"  Alt: {img.get('alt')}")
        
        if data.get('description'):
            lines.append(f"Description: {data['description']}")
    
    # Crawled site data (multiple pages)
    elif 'pages' in data and data['pages']:
        total_pages = len(data['pages'])
        lines.append(f"=== SCRAPED WEBSITE ({total_pages} pages) ===")
        
        if wants_urls or wants_all:
            lines.append("--- ALL URLs FROM ALL PAGES ---")
            for i, page in enumerate(data['pages'], 1):
                lines.append(f"Page {i}: {page.get('url', 'N/A')}")
        
        if wants_paragraphs or wants_all or wants_more:
            lines.append("--- ALL PARAGRAPHS ---")
            for i, page in enumerate(data['pages'], 1):
                paras = page.get('paragraphs', [])
                if paras:
                    lines.append(f"Page {i} ({page.get('title', 'N/A')}):")
                    for j, p in enumerate(paras, 1):
                        lines.append(f"  [{j}]: {p}")
        
        if wants_headings or wants_all:
            lines.append("--- ALL HEADINGS ---")
            for i, page in enumerate(data['pages'], 1):
                headings = page.get('headings', {})
                if headings:
                    lines.append(f"Page {i}: {page.get('title', 'N/A')}")
                    for level in ['h1', 'h2', 'h3']:
                        if headings.get(level):
                            for h in headings[level][:5]:
                                lines.append(f"  {level.upper()}: {h}")
        
        if wants_images or wants_all:
            lines.append("--- ALL IMAGES ---")
            for i, page in enumerate(data['pages'], 1):
                imgs = page.get('images', [])
                if imgs:
                    lines.append(f"Page {i}: {page.get('title', 'N/A')}")
                    for img in imgs[:10]:
                        lines.append(f"  • {img.get('url', 'N/A')}")
        
        if wants_edit or wants_all:
            lines.append("--- DATA FOR MODIFICATION ---")
            for i, page in enumerate(data['pages'][:10], 1):
                lines.append(f"Page {i}: {page.get('title', 'N/A')} | URL: {page.get('url', 'N/A')}")
    
    lines.append(f"QUESTION: {question}")
    if wants_edit:
        lines.append("Make the requested changes to the data above.")
    
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
            "mode": "gemini-3-flash-preview"
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

