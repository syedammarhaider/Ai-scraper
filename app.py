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

# Mount static files if needed
os.makedirs("downloads", exist_ok=True)

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

    print(f"🚀 Starting scrape: {url} with mode: {mode}")
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
You are an EXACT factual AI.

Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say:
"This information is not available in the scraped website data."
3. Never guess.
4. Never use outside knowledge.
"""

    context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:15000]}\n\nQUESTION:\n{message}"

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
                {"role": "user", "content": full_context}
            ],
            temperature=0.2,
            max_tokens=8000
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
        "pdf": scraper.save_as_pdf,
        "markdown": scraper.save_as_text  # Use text handler for markdown
    }

    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}

    path = handlers[fmt](data, filename)
    return FileResponse(path, filename=os.path.basename(path))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)