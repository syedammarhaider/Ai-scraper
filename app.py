# ==========================================================
# app.py
# Optimized AI Scraper + Groq AI System (FAST VERSION)
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
import time

from scraper import UltraScraper

# ==========================================================
# ENV LOAD
# ==========================================================

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL = "llama-3.3-70b-versatile"

# ==========================================================
# APP INIT
# ==========================================================

app = FastAPI()

templates = Jinja2Templates(directory="templates")

scraper = UltraScraper()

# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# STATIC
# ==========================================================

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================================
# ERROR HANDLER
# ==========================================================

@app.exception_handler(Exception)
async def error_handler(request: Request, exc: Exception):

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc)
        }
    )

# ==========================================================
# GROQ CLIENT
# ==========================================================

class GroqClient:

    def __init__(self, api_key):

        self.url = "https://api.groq.com/openai/v1/chat/completions"

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def ask(self, messages, temperature=0.2):

        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2000
        }

        response = requests.post(
            self.url,
            headers=self.headers,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            raise Exception(f"Groq API Error {response.status_code}")

        return response.json()


groq_ai = GroqClient(GROQ_API_KEY)

# ==========================================================
# HOME
# ==========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):

    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# ==========================================================
# HEALTH
# ==========================================================

@app.get("/health")
async def health():

    return {"status": "ok"}

# ==========================================================
# SCRAPE
# ==========================================================

@app.post("/scrape")
async def scrape(request: Request):

    try:

        form = await request.form()

        url = form.get("url")

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        data = scraper.crawl_website(url)

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
# CONTEXT BUILDER (FAST)
# ==========================================================

def build_context(data):

    parts = []

    if data.get("title"):
        parts.append("TITLE:\n" + data["title"])

    if data.get("description"):
        parts.append("DESCRIPTION:\n" + data["description"])

    if data.get("headings"):
        parts.append(
            "HEADINGS:\n" +
            "\n".join(data["headings"][:20])
        )

    if data.get("paragraphs"):
        parts.append(
            "CONTENT:\n" +
            "\n".join(data["paragraphs"][:30])
        )

    return "\n\n".join(parts)

# ==========================================================
# AI QUESTION ANSWER
# ==========================================================

@app.post("/groq-chat")
async def chat(request: Request):

    form = await request.form()

    question = form.get("message")
    scraped = form.get("scraped_data")

    if not question or not scraped:
        return {"success": False, "error": "Missing input"}

    try:

        data = json.loads(scraped)

    except:

        return {"success": False, "error": "Invalid JSON"}

    context = build_context(data)

    system_prompt = """
You are a factual AI assistant.

Rules:
Only answer using provided website data.
If answer missing say:
"Information not found in scraped website."
"""

    messages = [

        {"role": "system", "content": system_prompt},

        {
            "role": "user",
            "content": f"""
WEBSITE DATA:

{context}

QUESTION:
{question}
"""
        }
    ]

    try:

        response = groq_ai.ask(messages)

        answer = response["choices"][0]["message"]["content"]

        return {
            "success": True,
            "response": answer
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }

# ==========================================================
# GROK MODE
# ==========================================================

@app.post("/grok-mode")
async def grok_mode(request: Request):

    form = await request.form()

    message = form.get("message")

    if not message:
        return {"success": False, "error": "Question required"}

    messages = [

        {
            "role": "system",
            "content": "You are an expert AI assistant."
        },

        {
            "role": "user",
            "content": message
        }
    ]

    try:

        response = groq_ai.ask(messages, temperature=0.4)

        answer = response["choices"][0]["message"]["content"]

        return {
            "success": True,
            "response": answer
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }

# ==========================================================
# EXPORT
# ==========================================================

@app.post("/export")
async def export(request: Request):

    body = await request.json()

    fmt = body.get("format")
    data = body.get("data")

    handlers = {

        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }

    if fmt not in handlers:
        return {"success": False, "error": "Invalid format"}

    path = handlers[fmt](data, "scraped_data")

    return FileResponse(
        path,
        filename=os.path.basename(path)
    )
