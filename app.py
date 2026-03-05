# app.py - Professional AI Scraper Q&A System
# Roman Urdu comments added har line ke upar

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, json, time, uuid
import requests

from scraper import UltraScraper  # Custom scraper import

# ------------------- ENVIRONMENT -------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# ------------------- INIT FASTAPI -------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------------- GLOBAL ERROR HANDLER -------------------
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
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat_completions_create(self, model, messages, temperature=0, max_tokens=16000, **kwargs):
        try:
            data = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            data.update(kwargs)
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=60
            )
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
        print("✅ Groq clients initialized successfully (Direct API)")
        return True
    except Exception as e:
        print(f"⚠️ Direct initialization failed: {e}")
        try:
            from groq import Groq
            groq_ai = Groq(api_key=GROQ_API_KEY)
            grok_mode = Groq(api_key=GROQ_API_KEY)
            print("✅ Groq clients initialized (Standard API)")
            return True
        except Exception as e2:
            print(f"❌ All initialization methods failed: {e2}")
            groq_ai = None
            grok_mode = None
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

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        data["session_id"] = str(uuid.uuid4())
        return {"success": True, "data": data}

    except Exception as e:
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

# ------------------- UTILITIES -------------------
def split_text_into_chunks(text, max_words=1500):
    """Boht lamba scraped text ko manageable chunks mein divide karta hai"""
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_words):
        chunks.append(" ".join(words[i:i+max_words]))
    return chunks

def groq_request_with_retry(client, model, messages, max_retries=3):
    """429 error ke liye retry logic with exponential backoff"""
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
    """
    Ye endpoint scraped JSON data ko read karta hai
    aur kisi bhi question ka professional answer deta hai
    sirf aur sirf scraped data se.
    """
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

    # System prompt for professional Q&A
    system_prompt = """You are a professional AI assistant trained to answer any question
only using the provided scraped JSON data.
Rules:
1. Use only data from JSON, nothing outside.
2. Never say "information not available" if data exists.
3. Provide precise, structured, factual answers.
4. Preserve links, URLs, lists, and keys if present.
5. Be concise and professional.
"""

    # Include only relevant fields to reduce token usage
    relevant_data = {
        "url": data.get("url", ""),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "paragraphs": data.get("paragraphs", []),
        "links": data.get("links", []),
        "urls": data.get("urls", [])
    }

    context_text = json.dumps(relevant_data, indent=2)
    chunks = split_text_into_chunks(context_text, max_words=1500)
    aggregated_answers = []

    # Process each chunk with retry
    for chunk in chunks:
        messages_to_send = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"SCRAPED JSON DATA:\n{chunk}\n\nQUESTION:\n{message}"}
        ]
        response = groq_request_with_retry(groq_ai, MODEL, messages_to_send)
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
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

# ------------------- GROK MODE -------------------
@app.post("/grok-mode")
async def grok_mode_endpoint(request: Request):
    try:
        form = await request.form()
        message = form.get("message")
        analysis_type = form.get("analysis_type", "comprehensive")
        if not message:
            return {"success": False, "error": "Missing message"}
        if not grok_mode:
            return {"success": False, "error": "Grok Mode client not initialized"}

        system_prompt = f"""You are Grok Mode - advanced AI for universal questions.
Rules:
1. Use general knowledge only.
2. Ignore scraped data.
3. Be helpful, detailed, comprehensive.
4. Analysis Type: {analysis_type}
"""

        response = grok_mode.chat_completions_create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"USER QUESTION:\n{message}"}
            ],
            temperature=0.4,
            max_tokens=8000
        )

        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not answer:
            answer = "No response generated from Grok Mode."

        return {"success": True, "response": answer.strip(), "mode": "grok_mode", "analysis_type": analysis_type}

    except Exception as e:
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}

# ------------------- GROK SUMMARY -------------------
@app.post("/grok-summary")
async def grok_summary(request: Request):
    form = await request.form()
    scraped = form.get("scraped_data")
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    if not groq_ai:
        return {"success": False, "error": "Groq AI client not initialized"}

    data = json.loads(scraped)
    system_prompt = """You are GROK MODE SUMMARY - Extract key facts accurately.
Provide structured summary:
1. MAIN TOPIC
2. KEY POINTS (3-5)
3. STATISTICS
4. CONCLUSION
Use only data from JSON. If info missing, say "Not found".
"""

    context_parts = [f"URL: {data.get('url', '')}"]
    if data.get('title'):
        context_parts.append(f"Title: {data['title']}")
    if data.get('description'):
        context_parts.append(f"Description: {data['description']}")
    if data.get('paragraphs'):
        context_parts.append("\nContent:\n" + "\n".join(data['paragraphs'][:50]))
    if data.get('links'):
        context_parts.append("\nLinks:\n" + "\n".join(data['links']))
    if data.get('urls'):
        context_parts.append("\nURLs:\n" + "\n".join(data['urls']))

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
    return {"success": True, "summary": answer.strip(), "mode": "grok_summary"}