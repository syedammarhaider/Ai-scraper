# Updated app.py with Full Website Crawling Integration
# Har line ke upar Roman Urdu mein comment added hai ke ye line kya karti hai
# /scrape endpoint ab comprehensive mode mein crawl_website call karega for whole site scraping
# Other modes single page scrape karenge
# Groq integration as it is, but error handling improved
# Export functions as is

from fastapi import FastAPI, Request  # Ye imports FastAPI aur Request ke liye hain
from fastapi.responses import HTMLResponse, FileResponse  # Ye HTML aur File responses ke liye
from fastapi.templating import Jinja2Templates  # Ye templates ke liye
from fastapi.staticfiles import StaticFiles  # Ye static files serve ke liye
from dotenv import load_dotenv  # Ye .env load ke liye
import os, json, time, uuid  # Ye basic imports hain (os for paths, json for data, etc.)
import requests  # Ye requests import hai for direct Groq API

from scraper import UltraScraper  # Ye custom scraper import karti hai

# Load .env variables - Ye line .env file se variables load karti hai
load_dotenv()

# Initialize FastAPI - Ye line app create karti hai
app = FastAPI()
templates = Jinja2Templates(directory="templates")  # Ye templates set karti hai
scraper = UltraScraper()  # Ye scraper object create karti hai

# Mount static files - Ye line static files serve karta hai
app.mount("/static", StaticFiles(directory="static"), name="static")

# GROQ - Using direct API calls for Python 3.14 compatibility - Ye comment Groq ke bare mein hai
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Ye API key get karti hai
MODEL = "llama-3.3-70b-versatile"  # Ye model set karti hai
MODEL_DEEP = "llama-3.3-70b-versatile"  # Ye deep model set karti hai

# Direct Groq API client using requests for better compatibility - Ye class direct client banati hai
class GroqDirectClient:
    # Ye init function client initialize karta hai
    def __init__(self, api_key):
        self.api_key = api_key  # Ye API key save karti hai
        self.base_url = "https://api.groq.com/openai/v1"  # Ye base URL set karti hai
        self.headers = {  # Ye headers dictionary banati hai
            "Authorization": f"Bearer {api_key}",  # Ye auth header
            "Content-Type": "application/json"  # Ye content type
        }
    
    # Ye function chat completion create karta hai
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500, **kwargs):
        try:  # Ye try block error handle ke liye
            data = {  # Ye data dictionary banati hai
                "model": model,  # Ye model
                "messages": messages,  # Ye messages
                "temperature": temperature,  # Ye temperature
                "max_tokens": max_tokens  # Ye max tokens
            }
            data.update(kwargs)  # Ye extra kwargs add karti hai
            response = requests.post(  # Ye POST request bhejti hai
                f"{self.base_url}/chat/completions",  # Ye URL
                headers=self.headers,  # Ye headers
                json=data,  # Ye JSON data
                timeout=30  # Ye timeout
            )
            response.raise_for_status()  # Ye error check
            return response.json()  # Ye JSON return
        except Exception as e:  # Ye exception handle
            raise Exception(f"Groq API error: {str(e)}")  # Ye raise karti hai

# Global variables for Groq clients - Ye globals set karti hain
groq_ai = None  # Ye AI client
grok_mode = None  # Ye Grok client

# Initialize Groq clients with robust error handling - Ye function clients initialize karta hai
def initialize_grok_clients():
    global groq_ai, grok_mode  # Ye globals use karti hai
    try:  # Ye try block
        groq_ai = GroqDirectClient(GROQ_API_KEY)  # Ye AI client create
        grok_mode = GroqDirectClient(GROQ_API_KEY)  # Ye Grok client create
        print("✅ Groq clients initialized successfully (Direct API)")  # Ye success print
        return True  # Ye true return
    except Exception as e:  # Ye exception
        print(f"⚠️ Direct initialization failed: {e}")  # Ye error print
        try:  # Ye fallback try
            from groq import Groq  # Ye import try
            groq_ai = Groq(api_key=GROQ_API_KEY)  # Ye standard client
            grok_mode = Groq(api_key=GROQ_API_KEY)  # Ye standard Grok
            print("✅ Groq clients initialized (Standard API)")  # Ye print
            return True  # Ye return
        except Exception as e2:  # Ye exception
            print(f"❌ All initialization methods failed: {e2}")  # Ye print
            groq_ai = None  # Ye None set
            grok_mode = None  # Ye None set
            return False  # Ye false return

# Initialize clients at startup - Ye line function call karti hai
initialize_grok_clients()

# ========== HELPER FUNCTIONS ==========
# Ye helper function context size limit karne ke liye
def truncate_for_llm(obj, max_chars=24000):
    text = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    if len(text) > max_chars:
        text = text[:max_chars-10] + "... [truncated]"
    return text

# ========== HOME ==========
# Ye endpoint root par HTML serve karta hai
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})  # Ye template return karti hai

# ========== HEALTH ==========
# Ye endpoint health check karta hai
@app.get("/health")
async def health():
    return {"status": "healthy"}  # Ye status return

# ========== SCRAPE ==========
# Ye endpoint scrape karta hai, ab comprehensive mein crawl use karega for whole site
@app.post("/scrape")
async def scrape(request: Request):
    try:  # Ye try error handle ke liye
        form = await request.form()  # Ye form data get karti hai
        url = form.get("url")  # Ye URL get
        mode = form.get("mode", "comprehensive")  # Ye mode get, default comprehensive

        if not url:  # Ye check URL empty to nahi
            return {"success": False, "error": "URL required"}  # Ye error return

        if not url.startswith("http"):  # Ye check http nahi to add
            url = "https://" + url  # Ye https add

        print(f"🔍 Scraping URL: {url}, Mode: {mode}")  # Ye log print

        if mode == "comprehensive":  # Ye check comprehensive mode hai to crawl
            data = scraper.crawl_website(url, mode)  # Ye crawl call
        else:  # Ye else single scrape
            data = scraper.scrape_single_page(url, mode)  # Ye single call

        print(f"✅ Scraping completed for: {url}")  # Ye success print
        
        if "error" in data:   # Ye check error hai
            return {"success": False, "error": data["error"]}  # Ye error return
        
        data["session_id"] = str(uuid.uuid4())  # Ye session ID add (frontend ke liye)
        return {"success": True, "data": data}  # Ye success return
    
    except Exception as e:  # Ye exception handle
        print(f"❌ Scraping error: {str(e)}")  # Ye print
        return {"success": False, "error": f"Scraping failed: {str(e)}"}  # Ye return

# ========== GROQ CHAT ==========
# Ye endpoint Groq chat handle karta hai
@app.post("/groq-chat")
async def chat(request: Request):
    form = await request.form()  # Ye form get
    message = form.get("message")  # Ye message
    scraped = form.get("scraped_data")  # Ye scraped data
    if not message or not scraped:  # Ye check missing
        return {"success": False, "error": "Missing data"}  # Ye error
    if not groq_ai:  # Ye check client initialized nahi
        return {"success": False, "error": "Groq AI client not initialized"}  # Ye error

    data = json.loads(scraped)  # Ye JSON parse
    system_prompt = """  # Ye system prompt define
You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
5. For greetings, respond naturally but briefly.
"""
    
    # Handle both single page and aggregated crawl data with smart truncation
    if "pages" in data:  # Aggregated crawl data
        context_parts = [f"CRAWLED WEBSITE: {data.get('start_url', '')}"]
        context_parts.append(f"Total Pages Scraped: {data.get('total_stats', {}).get('pages_scraped', 0)}")
        context_parts.append(f"Total Paragraphs: {data.get('total_stats', {}).get('total_paragraphs', 0)}")
        context_parts.append("\nSCRAPED CONTENT FROM ALL PAGES:")
        
        # Add first few pages with limited content
        for i, page in enumerate(data.get("pages", [])[:8]):  # Limit to first 8 pages
            context_parts.append(f"\n--- PAGE {i+1}: {page.get('url', '')} ---")
            if page.get('title'):
                context_parts.append(f"Title: {page['title']}")
            if page.get('description'):
                context_parts.append(f"Description: {page['description'][:200]}")  # Truncate description
            if page.get('paragraphs'):
                # Limit paragraphs per page and truncate long ones
                paras = page['paragraphs'][:10]  # First 10 paragraphs
                truncated_paras = [p[:500] + "..." if len(p) > 500 else p for p in paras]
                context_parts.append("Content:\n" + "\n".join(truncated_paras))
        
        context = "\n".join(context_parts) + f"\n\nQUESTION:\n{message}"
        # Additional truncation if still too long
        if len(context) > 25000:
            context = context[:24990] + "... [truncated for size]"
    else:  # Single page data
        context = f"SCRAPED DATA (truncated for LLM):\n{truncate_for_llm(data)}\n\nQUESTION:\n{message}"

    try:  # Ye try
        response = groq_ai.chat_completions_create(  # Ye call
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0,
            max_tokens=1500
        )
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No answer returned").strip()  # Ye answer extract
        return {"success": True, "response": answer}  # Ye return
    except Exception as e:  # Ye exception
        return {"success": False, "error": f"Groq API error: {str(e)}"}  # Ye return

# ========== EXPORT ==========
# Ye endpoint export handle karta hai
@app.post("/export")
async def export(request: Request):
    body = await request.json()  # Ye JSON body get
    fmt = body.get("format")  # Ye format
    data = body.get("data")  # Ye data

    if not fmt or not data:  # Ye check missing
        return {"success": False, "error": "Missing format or data"}  # Ye error

    filename = f"scraped_data"  # Ye filename set

    handlers = {  # Ye handlers dictionary
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf
    }

    if fmt not in handlers:  # Ye check unsupported
        return {"success": False, "error": f"Unsupported format: {fmt}"}  # Ye error

    path = handlers[fmt](data, filename)  # Ye handler call
    return FileResponse(path, filename=os.path.basename(path))  # Ye file return

# ========== GROK MODE - ENHANCED AI ==========
# Ye endpoint Grok mode handle karta hai
@app.post("/grok-mode")
async def grok_mode_endpoint(request: Request):
    try:  # Ye try
        form = await request.form()  # Ye form
        message = form.get("message")  # Ye message
        scraped = form.get("scraped_data")  # Ye scraped
        analysis_type = form.get("analysis_type", "comprehensive")  # Ye type
        
        if not message or not scraped:  # Ye check
            return {"success": False, "error": "Missing message or scraped data"}  # Ye error
        if not grok_mode:  # Ye check
            return {"success": False, "error": "Grok Mode client not initialized"}  # Ye error
        
        try:  # Ye try
            data = json.loads(scraped)  # Ye parse
        except:  # Ye except
            return {"success": False, "error": "Invalid scraped data format"}  # Ye error
        
        system_prompt = f"""You are Grok Mode - an advanced AI assistant for universal questions.

Rules:
1. ONLY answer universal/general knowledge questions
2. DO NOT use scraped data - ignore any website content provided
3. Use your comprehensive knowledge for all answers
4. Be helpful, detailed, and comprehensive
5. Analysis Type: {analysis_type}

Provide expert answers on any topic using your knowledge base. The scraped data is irrelevant - focus on universal knowledge."""  # Ye prompt
        
        full_context = f"USER QUESTION:\n{message}\n\n(Note: This is a universal knowledge question. Provide comprehensive answer using your knowledge base.)"  # Ye context

        try:  # Ye try
            messages_to_send = [  # Ye messages list
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}
            ]
            
            response = grok_mode.chat_completions_create(  # Ye call
                model=MODEL_DEEP,
                messages=messages_to_send,
                temperature=0.4,
                max_tokens=8000
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", None)  # Ye extract
            if not answer:  # Ye check
                answer = "No response generated from Grok Mode."  # Ye default
            
            return {  # Ye return dictionary
                "success": True, 
                "response": answer.strip(),
                "mode": "grok_mode",
                "model": MODEL_DEEP,
                "analysis_type": analysis_type
            }
            
        except Exception as e:  # Ye except
            print("🔥 Grok Mode Exception:", e)  # Ye print
            return {"success": False, "error": f"Grok Mode error: {str(e)}"}  # Ye return
    
    except Exception as e:  # Ye general except
        print("🔥 Grok Mode General Exception:", e)  # Ye print
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}  # Ye return

# ========== GROK MODE SUMMARY ==========
# Ye endpoint summary handle karta hai
@app.post("/grok-summary")
async def grok_summary(request: Request):
    form = await request.form()  # Ye form
    scraped = form.get("scraped_data")  # Ye scraped
    
    if not scraped:  # Ye check
        return {"success": False, "error": "Missing scraped data"}  # Ye error
    if not groq_ai:  # Ye check
        return {"success": False, "error": "Groq AI client not initialized"}  # Ye error
    
    data = json.loads(scraped)  # Ye parse
    
    system_prompt = """You are GROK MODE SUMMARY - Extract key facts instantly and accurately.

Provide a structured summary with:
1. MAIN TOPIC - What the page/site is about
2. KEY POINTS - 3-5 most important facts
3. STATISTICS - Any numbers/data found
4. CONCLUSION - Main takeaway

Only use data from scraped content. If info missing, say "Not found"."""  # Ye prompt
    
    # Handle both single page and aggregated crawl data with smart truncation
    if "pages" in data:  # Aggregated crawl data
        context_parts = [f"CRAWLED WEBSITE: {data.get('start_url', '')}"]
        context_parts.append(f"Total Pages: {data.get('total_stats', {}).get('pages_scraped', 0)}")
        context_parts.append(f"Total Paragraphs: {data.get('total_stats', {}).get('total_paragraphs', 0)}")
        
        # Collect content from first few pages for summary
        page_titles = []
        all_paragraphs = []
        for page in data.get("pages", [])[:5]:  # First 5 pages
            if page.get('title'):
                page_titles.append(page['title'][:80])  # Truncate titles
            if page.get('paragraphs'):
                # Add limited paragraphs from each page
                page_paras = page['paragraphs'][:8]  # First 8 paragraphs
                truncated_paras = [p[:300] + "..." if len(p) > 300 else p for p in page_paras]
                all_paragraphs.extend(truncated_paras)
        
        if page_titles:
            context_parts.append(f"\nPage Titles: " + " • ".join(page_titles))
        if all_paragraphs:
            # Limit total paragraphs for summary
            context_parts.append(f"\nContent Sample:\n" + "\n".join(all_paragraphs[:20]))  # Max 20 paragraphs total
    else:  # Single page data
        context_parts = [f"URL: {data.get('url', '')[:300]}"]  # Truncate URL
        if data.get('title'):
            context_parts.append(f"Title: {data['title'][:180]}")  # Truncate title
        if data.get('description'):
            context_parts.append(f"Description: {data['description'][:500]}")  # Truncate description
        if data.get('paragraphs'):
            # Limit and truncate paragraphs
            short_paras = data['paragraphs'][:12]  # First 12 paragraphs
            truncated_paras = [p[:400] + "..." if len(p) > 400 else p for p in short_paras]
            context_parts.append("\nContent:\n" + "\n".join(truncated_paras))
    
    try:  # Ye try
        response = groq_ai.chat_completions_create(  # Ye call
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(context_parts)}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")  # Ye extract
        
        return {  # Ye return
            "success": True,
            "summary": answer.strip(),
            "mode": "grok_summary"
        }
        
    except Exception as e:  # Ye except
        return {"success": False, "error": f"Summary error: {str(e)}"}  # Ye return