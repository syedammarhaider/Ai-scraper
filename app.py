# app.py

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
from scraper import UltraScraper
import os, json, time

# Load .env variables
load_dotenv()

# Initialize FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
 
# ---------- GROQ ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Initialize Groq client without proxies
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ---------- HOME ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "healthy"}

# ---------- SCRAPE ----------
@app.post("/scrape")
async def scrape(request: Request):
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith("http"):
        url = "https://" + url

    data = scraper.scrape_website(url, mode)

    if "error" in data:
        return {"success": False, "error": data["error"]}

    return {"success": True, "data": data}

# ---------- GROQ CHAT ----------
@app.post("/groq-chat")
async def chat(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing data"}

    data = json.loads(scraped)

    system_prompt = """
You are an EXACT factual AI assistant.

Rules:
1. READ the scraped data content provided below in READABLE FORMAT
2. ANSWER the user's question directly using ONLY that content
3. The content is already structured for you - use it directly
4. If answer not found, say: "This information is not available in the scraped website data."
5. NEVER guess or use outside knowledge
6. IMPORTANT: Provide ANSWERS, not explanations about what data you have
"""

    # Construct readable context instead of raw JSON
    context_parts = ["SCRAPED DATA ANALYSIS:"]
    
    # Handle both single page and crawled data
    if 'pages' in data:
        # Multi-page crawl data
        context_parts.append(f"Website crawled: {data.get('start_url', 'Unknown')}")
        context_parts.append(f"Total pages scraped: {len(data['pages'])}")
        context_parts.append("")
        
        for i, page in enumerate(data['pages'][:10], 1):  # Show more pages
            context_parts.append(f"PAGE {i}: {page.get('title', 'No title')}")
            context_parts.append(f"URL: {page.get('url', 'Unknown')}")
            
            if page.get('description'):
                context_parts.append(f"Description: {page['description']}")
            
            # Add key headings
            if page.get('headings'):
                for level, headings in page['headings'].items():
                    if headings and len(headings) > 0:
                        context_parts.append(f"{level.upper()}: {', '.join(headings[:5])}")
            
            # Add first few paragraphs
            if page.get('paragraphs'):
                context_parts.append("Content:")
                for para in page['paragraphs'][:5]:
                    context_parts.append(f"- {para}")
            
            # Add internal links
            if page.get('internal_links'):
                context_parts.append("Internal Links:")
                for link in page['internal_links'][:10]:
                    context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")
            
            context_parts.append("")
    else:
        # Single page data
        context_parts.append(f"Page: {data.get('title', 'No title')}")
        context_parts.append(f"URL: {data.get('url', 'Unknown')}")
        
        if data.get('description'):
            context_parts.append(f"Description: {data['description']}")
        
        # Add headings
        if data.get('headings'):
            context_parts.append("Headings:")
            for level, headings in data['headings'].items():
                if headings and len(headings) > 0:
                    context_parts.append(f"{level.upper()}: {', '.join(headings[:5])}")
        
        # Add paragraphs
        if data.get('paragraphs'):
            context_parts.append("Content:")
            for para in data['paragraphs'][:10]:
                context_parts.append(f"- {para}")
        
        # Add images if available
        if data.get('images'):
            context_parts.append("Images:")
            for img in data['images'][:5]:
                context_parts.append(f"- {img.get('alt', 'No alt text')}: {img.get('url', 'No URL')}")
        
        # Add links if available
        if data.get('internal_links'):
            context_parts.append("Internal Links:")
            for link in data['internal_links'][:10]:
                context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")
        
        # Add external links if available
        if data.get('external_links'):
            context_parts.append("External Links:")
            for link in data['external_links'][:10]:
                context_parts.append(f"- {link.get('text', 'No text')}: {link.get('url', 'No URL')}")
    
    context_parts.append(f"\nQUESTION: {message}")
    context = "\n".join(context_parts)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0,
            max_tokens=1500
        )

        answer = getattr(getattr(response.choices[0], "message", None), "content", None)
        if not answer:
            answer = "Groq API did not return any answer."

        return {"success": True, "response": answer.strip()}

    except Exception as e:
        return {"success": False, "error": f"Groq API error: {str(e)}"}

# ---------- GROK MODE ----------
@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    analysis_type = form.get("analysis_type", "comprehensive")

    if not message or not scraped:
        return {"success": False, "error": "Missing message or scraped data"}

    data = json.loads(scraped)

    system_prompt = (
        "You are GROK MODE - An advanced AI for universal questions. "
        "RULES: 1. UNIVERSAL KNOWLEDGE ONLY - Use your comprehensive knowledge base. "
        "2. DO NOT use scraped data - ignore website content. "
        "3. PROVIDE expert answers on any topic. "
        "4. BE helpful and comprehensive. "
        "5. Use your full knowledge for all responses."
    )

    full_context = f"USER QUESTION:\n{message}\n\n(Note: This is a universal knowledge question. Provide comprehensive answer using your knowledge base.)"

    try:
        response = client.chat.completions.create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}  # Removed character limit for unlimited answers
            ],
            temperature=0.2,
            max_tokens=8000  # Increased from 2000 to 8000 for much longer answers
        )

        answer = getattr(response.choices[0].message, 'content', None)
        if not answer:
            answer = "No response generated."

        return {"success": True, "response": answer.strip(), "mode": "grok_mode"}

    except Exception as e:
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}

# ---------- GROK SUMMARY ----------
@app.post("/grok-summary")
async def grok_summary(request: Request):
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    scraped = form.get("scraped_data")

    if not scraped:
        return {"success": False, "error": "Missing scraped data"}

    data = json.loads(scraped)

    system_prompt = (
        "GROK SUMMARY - Extract key facts. "
        "Provide: 1. MAIN TOPIC. 2. KEY POINTS (3-5). 3. STATISTICS. 4. CONCLUSION. "
        "Only use page data."
    )

    context_parts = ["URL: " + data.get('url', '')]
    if data.get('title'):
        context_parts.append("Title: " + data['title'])
    if data.get('paragraphs'):
        context_parts.append("\n".join(data['paragraphs'][:15]))

    try:
        response = client.chat.completions.create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(context_parts)}
            ],
            temperature=0.1,
            max_tokens=500
        )

        answer = getattr(response.choices[0].message, 'content', 'No summary.')
        return {"success": True, "summary": answer.strip(), "mode": "grok_summary"}

    except Exception as e:
        return {"success": False, "error": f"Summary error: {str(e)}"}

# ---------- EXPORT ----------
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