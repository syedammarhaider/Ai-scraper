# ==========================================================
# app.py
# Full Website Scraping + Groq/Grok AI Question Answer System
# Roman Urdu comments har important section ke upar diye gaye hain
# ==========================================================

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

import os
import json
import uuid
import requests

from scraper import UltraScraper

# ==========================================================
# ENVIRONMENT VARIABLES LOAD KARNA
# ==========================================================

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# ==========================================================
# FASTAPI APP INITIALIZE
# ==========================================================

app = FastAPI()

templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# ==========================================================
# CORS CONFIGURATION
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# STATIC FILES SERVE KARNA
# ==========================================================

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================================
# GLOBAL ERROR HANDLER
# ==========================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": f"Server error: {str(exc)}"
        }
    )

# ==========================================================
# GROQ API CLIENT
# ==========================================================

class GroqDirectClient:

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat_completions_create(self, model, messages, temperature=0, max_tokens=16000):

        try:

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
            )

            response.raise_for_status()

            return response.json()

        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")


# ==========================================================
# GROQ CLIENT INITIALIZATION
# ==========================================================

groq_ai = None
grok_mode = None


def initialize_grok_clients():

    global groq_ai, grok_mode

    try:

        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode = GroqDirectClient(GROQ_API_KEY)

        print("✅ Groq clients initialized successfully")

        return True

    except Exception as e:

        print("❌ Groq initialization failed:", e)

        groq_ai = None
        grok_mode = None

        return False


initialize_grok_clients()

# ==========================================================
# HOME PAGE
# ==========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):

    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# ==========================================================
# HEALTH CHECK ENDPOINT
# ==========================================================

@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }

# ==========================================================
# WEBSITE SCRAPER ENDPOINT
# ==========================================================

@app.post("/scrape")
async def scrape(request: Request):

    try:

        form = await request.form()

        url = form.get("url")
        mode = form.get("mode", "comprehensive")

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        print(f"🔎 Scraping: {url}")

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        data["session_id"] = str(uuid.uuid4())

        return {
            "success": True,
            "data": data
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }

# ==========================================================
# TEXT CHUNKING FUNCTION
# Large scraped JSON ko chunks mein divide karta hai
# ==========================================================

def split_text_into_chunks(text, chunk_size=4000):

    words = text.split()

    chunks = []
    current_chunk = []
    current_length = 0

    for word in words:

        current_chunk.append(word)
        current_length += len(word) + 1

        if current_length >= chunk_size:

            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

# ==========================================================
# GROQ QUESTION ANSWER SYSTEM
# ==========================================================

@app.post("/groq-chat")
async def chat(request: Request):

    form = await request.form()

    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing input data"}

    if not groq_ai:
        return {"success": False, "error": "Groq client not initialized"}

    try:
        data = json.loads(scraped)
    except:
        return {"success": False, "error": "Invalid JSON"}

    system_prompt = """
You are a factual AI assistant.

Rules:
1. Only answer using scraped data.
2. If answer not present say:
"This information is not available in the scraped website data."
3. Never guess.
4. Be precise.
"""

    context_text = json.dumps(data, indent=2)

    chunks = split_text_into_chunks(context_text)

    answers = []

    for chunk in chunks:

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"SCRAPED DATA:\n{chunk}\n\nQUESTION:\n{message}"}
        ]

        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=messages,
            temperature=0,
            max_tokens=4000
        )

        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        answers.append(answer.strip())

    final_answer = "\n\n".join(answers)

    return {
        "success": True,
        "response": final_answer
    }

# ==========================================================
# DATA EXPORT SYSTEM
# ==========================================================

@app.post("/export")
async def export(request: Request):

    body = await request.json()

    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

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

    return FileResponse(
        path,
        filename=os.path.basename(path)
    )

# ==========================================================
# GROK MODE - Universal Knowledge Questions
# ==========================================================

@app.post("/grok-mode")
async def grok_mode_endpoint(request: Request):
    
    try:
        
        form = await request.form()
        
        message = form.get("message")
        scraped = form.get("scraped_data")
        analysis_type = form.get("analysis_type", "comprehensive")

        if not message or not scraped:
            return {"success": False, "error": "Missing message or scraped data"}
        
        if not grok_mode:
            return {"success": False, "error": "Grok Mode client not initialized"}

        system_prompt = f"""You are Grok Mode - an advanced AI assistant for universal questions.
Rules:
1. ONLY answer universal/general knowledge questions
2. DO NOT use scraped data - ignore any website content provided
3. Use your comprehensive knowledge for all answers
4. Be helpful, detailed, and comprehensive
5. Analysis Type: {analysis_type}
"""

        full_context = f"USER QUESTION:\n{message}\n\n(Note: Provide comprehensive expert answer.)"

        response = grok_mode.chat_completions_create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}
            ],
            temperature=0.4,
            max_tokens=8000
        )
        
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not answer:
            answer = "No response generated from Grok Mode."

        return {
            "success": True,
            "response": answer.strip(),
            "mode": "grok_mode",
            "model": MODEL_DEEP,
            "analysis_type": analysis_type
        }

    except Exception as e:
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}

# ==========================================================
# GROK SUMMARY - Quick Summary Generator
# ==========================================================

@app.post("/grok-summary")
async def grok_summary(request: Request):
    
    form = await request.form()
    
    scraped = form.get("scraped_data")
    
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    
    if not groq_ai:
        return {"success": False, "error": "Groq AI client not initialized"}

    data = json.loads(scraped)
    
    system_prompt = """You are GROK MODE SUMMARY - Extract key facts instantly and accurately.
Provide structured summary:
1. MAIN TOPIC
2. KEY POINTS (3-5)
3. STATISTICS
4. CONCLUSION
Only use data from the page. If info missing, say "Not found".
"""

    context_parts = [f"URL: {data.get('url', '')}"]
    
    if data.get('title'):
        context_parts.append(f"Title: {data['title']}")
    
    if data.get('description'):
        context_parts.append(f"Description: {data['description']}")
    
    if data.get('paragraphs'):
        context_parts.append("\nContent:\n" + "\n".join(data['paragraphs'][:50]))

    response = groq_ai.chat_completions_create(
        model=MODEL_DEEP,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(context_parts)}
        ],
        temperature=0.1,
        max_tokens=5000
    )
    
    answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")
    
    return {
        "success": True, 
        "summary": answer.strip(), 
        "mode": "grok_summary"
    }