# app.py - Ultimate Professional AI Scraper Q&A System
# Roman Urdu comments included

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, json, time, uuid, re
import requests
from typing import List

from scraper import UltraScraper  # Custom scraper import

# ------------------- ENV -------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# ------------------- INIT FASTAPI -------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------------- GLOBAL ERROR -------------------
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Server error: {str(exc)}"},
    )

# ------------------- GROQ CLIENT -------------------
class GroqDirectClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def chat_completions_create(self, model, messages, temperature=0, max_tokens=16000, **kwargs):
        try:
            data = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            data.update(kwargs)
            response = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=data, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")

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
        print(f"⚠️ Initialization failed: {e}")
        return False

initialize_grok_clients()

# ------------------- HOME -------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ------------------- HEALTH -------------------
@app.get("/health")
async def health():
    return {"status": "healthy"}

# ------------------- SCRAPE -------------------
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

        data = scraper.crawl_website(url, mode) if mode == "comprehensive" else scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        data["session_id"] = str(uuid.uuid4())
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

# ------------------- UTILITIES -------------------
def split_text_semantic(text_list: List[str], max_words=1000) -> List[str]:
    """Semantic chunking: split by paragraph/logical section"""
    chunks = []
    current_chunk = []
    current_len = 0
    for para in text_list:
        words_len = len(para.split())
        if current_len + words_len > max_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(para)
        current_len += words_len
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def rank_chunks_by_relevance(chunks: List[str], question: str) -> List[str]:
    """Simple keyword match relevance"""
    question_words = set(re.findall(r"\w+", question.lower()))
    scored = []
    for chunk in chunks:
        chunk_words = set(re.findall(r"\w+", chunk.lower()))
        score = len(question_words & chunk_words)
        scored.append((score, chunk))
    scored.sort(reverse=True)
    return [c for s, c in scored if s > 0] or chunks  # fallback if no match

def groq_request_retry(client, model, messages, max_retries=3):
    """Retry for 429 errors"""
    for attempt in range(max_retries):
        try:
            return client.chat_completions_create(model, messages)
        except Exception as e:
            if "429" in str(e):
                wait_time = 2 ** attempt
                print(f"429 error detected, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("Max retries exceeded due to 429 errors.")

# ------------------- PROFESSIONAL SCRAPED Q&A -------------------
@app.post("/groq-chat")
async def chat(request: Request):
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing question or scraped data"}
    if not groq_ai:
        return {"success": False, "error": "Groq AI client not initialized"}

    try:
        data = json.loads(scraped)
    except:
        return {"success": False, "error": "Invalid scraped JSON"}

    # Validate non-empty
    if not any([data.get("paragraphs"), data.get("links"), data.get("urls"), data.get("title"), data.get("description")]):
        return {"success": False, "error": "Scraper returned empty data. Please scrape a valid page."}

    # Relevant fields
    relevant_data = {
        "url": data.get("url", ""),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "paragraphs": data.get("paragraphs", []),
        "links": data.get("links", []),
        "urls": data.get("urls", [])
    }

    # Semantic chunking
    text_blocks = relevant_data["paragraphs"] + relevant_data.get("links", []) + relevant_data.get("urls", [])
    chunks = split_text_semantic(text_blocks, max_words=1000)
    ranked_chunks = rank_chunks_by_relevance(chunks, message)

    # System prompt
    system_prompt = """You are a professional AI assistant trained to answer any question
only using the provided scraped JSON data. Provide structured, precise, factual answers.
Include lists, URLs, paragraphs if relevant. Always professional tone."""

    aggregated_answers = []
    for chunk in ranked_chunks:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"SCRAPED DATA CHUNK:\n{chunk}\n\nQUESTION:\n{message}"}
        ]
        response = groq_request_retry(groq_ai, MODEL, messages)
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if answer:
            aggregated_answers.append(answer.strip())

    final_answer = "\n\n".join(aggregated_answers)
    return {"success": True, "response": final_answer}

# ------------------- EXPORT -------------------
@app.post("/export")
async def export(request: Request):
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")
    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

    filename = f"scraped_data"
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