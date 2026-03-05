# Updated app.py with Full Website Crawling Integration
# Har line ke upar Roman Urdu mein comment added hai ke ye line kya karti hai
# /scrape endpoint ab comprehensive mode mein crawl_website call karega for whole site scraping
# Other modes single page scrape karenge
# Groq integration with unlimited context handling
# Export functions as is

from fastapi import FastAPI, Request  # Ye imports FastAPI aur Request ke liye hain
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse  # Ye HTML aur File responses ke liye
from fastapi.templating import Jinja2Templates  # Ye templates ke liye
from fastapi.staticfiles import StaticFiles  # Ye static files serve ke liye
from fastapi.middleware.cors import CORSMiddleware  # Ye CORS handle ke liye
from dotenv import load_dotenv  # Ye .env load ke liye
import os, json, time, uuid  # Ye basic imports hain (os for paths, json for data, etc.)
import requests  # Ye requests import hai for direct Groq API
import tiktoken  # Token counting ke liye

from scraper import UltraScraper  # Ye custom scraper import karti hai

# Load .env variables - Ye line .env file se variables load karti hai
load_dotenv()

# Initialize FastAPI - Ye line app create karti hai
app = FastAPI()
templates = Jinja2Templates(directory="templates")  # Ye templates set karti hai
scraper = UltraScraper()  # Ye scraper object create karti hai

# Add CORS middleware - Ye line CORS enable karti hai
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production mein specific domain set karein
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files - Ye line static files serve karti hai
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global exception handler - Ye HTML response ki jagah JSON return karta hai
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Server error: {str(exc)}"},
    )

# GROQ - Using direct API calls for Python 3.14 compatibility - Ye comment Groq ke bare mein hai
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Ye API key get karti hai
MODEL = "llama-3.3-70b-versatile"  # Ye model set karti hai
MODEL_DEEP = "llama-3.3-70b-versatile"  # Ye deep model set karti hai

# Token counter function - context length monitor karne ke liye
def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Approximate token count using tiktoken"""
    try:
        encoding = tiktoken.get_encoding(model)
        return len(encoding.encode(text))
    except:
        # Fallback: rough estimate (4 chars per token)
        return len(text) // 4

# Context chunking function - bade context ko chunks mein todna
def chunk_context(context: str, max_tokens: int = 120000, overlap: int = 1000):
    """Context ko chunks mein todta hai agar bohat bada ho"""
    tokens = count_tokens(context)
    
    if tokens <= max_tokens:
        return [context]  # Ek hi chunk mein sab
    
    chunks = []
    words = context.split()
    chunk_size = max_tokens * 3  # Approx words (har token ~3 chars)
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        if len(chunks) >= 5:  # Max 5 chunks to avoid rate limits
            break
    
    return chunks

# Context summarizer - har chunk ka summary banata hai
def summarize_chunk(chunk: str, client, chunk_num: int, total_chunks: int):
    """Har chunk ka summary banata hai taake overall context chota ho"""
    prompt = f"""This is chunk {chunk_num} of {total_chunks} from a scraped website.
Summarize the key information from this chunk concisely but comprehensively.
Focus on facts, data, and important points that would help answer questions about the website.

CHUNK CONTENT:
{chunk[:5000]}  # Sirf 5000 chars summarize karne ke liye

Provide a concise summary of the main points:"""
    
    try:
        response = client.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a precise summarizer. Extract key information only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1000
        )
        summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return summary
    except:
        return f"[Chunk {chunk_num} summary failed - using first 500 chars: {chunk[:500]}]"

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
                timeout=60  # Timeout increase kiya for large contexts
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
        
        # Count total pages scraped
        pages_count = len(data.get("pages", [])) if "pages" in data else 1
        
        data["session_id"] = str(uuid.uuid4())  # Ye session ID add (frontend ke liye)
        data["pages_count"] = pages_count  # Total pages count
        
        return {"success": True, "data": data}  # Ye success return
    
    except Exception as e:  # Ye exception handle
        print(f"❌ Scraping error: {str(e)}")  # Ye print
        return {"success": False, "error": f"Scraping failed: {str(e)}"}  # Ye return

# ========== GROQ CHAT (Single Page) ==========
# Ye endpoint Groq chat handle karta hai for single page
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
    system_prompt = """You are an EXACT factual AI assistant.
Rules:
1. ONLY answer from provided scraped data.
2. If answer not found, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge.
4. Be precise and factual.
5. For greetings, respond naturally but briefly.
"""
    context = f"SCRAPED DATA:\n{json.dumps(data, indent=2)[:8000]}\n\nQUESTION:\n{message}"  # Ye context banati hai

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

# ========== GROK MODE - ENHANCED AI FOR FULL WEBSITE ==========
# Ye endpoint Grok mode handle karta hai with unlimited context for whole website
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
        
        # Check if this is comprehensive data with multiple pages
        is_multi_page = "pages" in data and isinstance(data["pages"], list) and len(data["pages"]) > 0
        
        if is_multi_page:
            # MULTI-PAGE WEBSITE HANDLING - Unlimited context ke liye
            pages = data.get("pages", [])
            total_pages = len(pages)
            
            print(f"📚 Processing website with {total_pages} pages for Grok Mode")
            
            # Build comprehensive context from all pages
            website_context_parts = [
                f"=== WEBSITE OVERVIEW ===",
                f"Total Pages Scraped: {total_pages}",
                f"Main URL: {data.get('url', 'N/A')}",
                f"Site Title: {data.get('title', 'N/A')}",
                f"Site Description: {data.get('description', 'N/A')}",
                "\n=== DETAILED PAGE CONTENT ===\n"
            ]
            
            # Har page ka content add karo
            for idx, page in enumerate(pages, 1):
                page_url = page.get("url", f"Page {idx}")
                page_title = page.get("title", "No Title")
                
                page_content = [
                    f"\n--- PAGE {idx}/{total_pages}: {page_title} ---",
                    f"URL: {page_url}",
                ]
                
                # Page description
                if page.get("description"):
                    page_content.append(f"Description: {page['description']}")
                
                # Headings
                if page.get("headings"):
                    headings = page["headings"]
                    page_content.append(f"Heading: {headings.get('h1', [''])[0] if headings.get('h1') else 'No H1'}")
                
                # Paragraphs - unlimited paragraphs (sirf character limit ke liye check)
                if page.get("paragraphs"):
                    para_text = "\n".join(page["paragraphs"])
                    page_content.append(f"\nCONTENT:\n{para_text}")
                
                # Lists
                if page.get("lists"):
                    lists_text = "\n".join([f"• {item}" for sublist in page["lists"] for item in sublist])
                    page_content.append(f"\nLISTS:\n{lists_text}")
                
                # Tables
                if page.get("tables"):
                    tables_summary = f"Contains {len(page['tables'])} data tables"
                    page_content.append(f"\nTABLES: {tables_summary}")
                
                # Meta data
                if page.get("meta"):
                    meta_info = ", ".join([f"{k}: {v[:50]}" for k, v in list(page["meta"].items())[:5]])
                    page_content.append(f"Meta: {meta_info}")
                
                website_context_parts.append("\n".join(page_content))
            
            # Poora context banao
            full_context = "\n".join(website_context_parts)
            
            # Token count check karo
            token_count = count_tokens(full_context)
            print(f"📊 Total context tokens: {token_count}")
            
            # System prompt for full website analysis
            system_prompt = f"""You are GROK MODE - Advanced AI for COMPLETE WEBSITE ANALYSIS.

You have access to ALL pages of a scraped website ({total_pages} pages total).

RULES:
1. ANSWER FROM WEBSITE CONTENT - Use information from ANY page in the scraped data
2. CROSS-REFERENCE - If information spans multiple pages, combine it
3. SPECIFIC PAGE QUERIES - If user asks about a specific page, focus on that page's content
4. GENERAL WEBSITE QUERIES - For overall questions, use all pages
5. NO OUTSIDE KNOWLEDGE - Only use the provided website content
6. BE COMPREHENSIVE - Provide detailed answers using all relevant pages
7. CITE SOURCES - Mention which page(s) the information comes from

Analysis Type: {analysis_type}

The scraped data contains {total_pages} pages with complete content. Answer questions thoroughly using ALL available pages."""
            
            # Check agar context bohat bada hai to summarize karo
            if token_count > 80000:  # Agar 80k tokens se zyada
                print("⚠️ Large context detected, creating summary first...")
                
                # Pehle 20 pages ka full context do, baaki ka summary
                if total_pages > 20:
                    # Pehle 20 pages full
                    first_pages_context = "\n".join(website_context_parts[:20])
                    
                    # Baaki pages ka summary banao
                    remaining_summaries = []
                    for idx in range(20, total_pages):
                        page = pages[idx]
                        page_summary = f"Page {idx+1}: {page.get('title', 'No Title')} - {page.get('description', '')[:200]}"
                        remaining_summaries.append(page_summary)
                    
                    summary_text = "\n".join(remaining_summaries)
                    full_context = first_pages_context + f"\n\n=== REMAINING PAGES SUMMARY ===\n{summary_text}"
            
            # User question add karo
            user_context = f"WEBSITE CONTENT (All {total_pages} pages):\n\n{full_context[:150000]}\n\nUSER QUESTION: {message}\n\nProvide a comprehensive answer using ALL relevant pages. If the question is about a specific page, focus there. Otherwise, use the entire website."
            
        else:
            # SINGLE PAGE HANDLING - as before
            print("📄 Processing single page for Grok Mode")
            system_prompt = f"""You are Grok Mode - an advanced AI assistant for universal questions.

Rules:
1. ONLY answer universal/general knowledge questions
2. DO NOT use scraped data - ignore any website content provided
3. Use your comprehensive knowledge for all answers
4. Be helpful, detailed, and comprehensive
5. Analysis Type: {analysis_type}

Provide expert answers on any topic using your knowledge base. The scraped data is irrelevant - focus on universal knowledge."""
            
            user_context = f"USER QUESTION:\n{message}\n\n(Note: This is a universal knowledge question. Provide comprehensive answer using your knowledge base.)"

        try:  # Ye try
            messages_to_send = [  # Ye messages list
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context[:150000]}  # 150k chars limit safe side ke liye
            ]
            
            response = grok_mode.chat_completions_create(  # Ye call
                model=MODEL_DEEP,
                messages=messages_to_send,
                temperature=0.4,
                max_tokens=8000  # Max response length
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", None)  # Ye extract
            if not answer:  # Ye check
                answer = "No response generated from Grok Mode."  # Ye default
            
            return {  # Ye return dictionary
                "success": True, 
                "response": answer.strip(),
                "mode": "grok_mode",
                "model": MODEL_DEEP,
                "analysis_type": analysis_type,
                "pages_analyzed": total_pages if is_multi_page else 1,
                "context_tokens": token_count if is_multi_page else "N/A"
            }
            
        except Exception as e:  # Ye except
            print("🔥 Grok Mode Exception:", e)  # Ye print
            
            # Agar context size ki waja se error aya to try with smaller context
            if "context" in str(e).lower() or "token" in str(e).lower():
                print("⚠️ Context too large, trying with reduced context...")
                
                # Reduced context with just page titles and first paragraphs
                if is_multi_page:
                    reduced_context = []
                    for page in pages[:10]:  # Sirf 10 pages
                        reduced_context.append(f"Page: {page.get('title', 'No Title')}")
                        reduced_context.append(f"URL: {page.get('url', '')}")
                        if page.get('paragraphs'):
                            reduced_context.append("First paragraph: " + page['paragraphs'][0][:500])
                    
                    fallback_context = "\n".join(reduced_context)
                    
                    try:
                        response = grok_mode.chat_completions_create(
                            model=MODEL,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"Based on these website excerpts:\n\n{fallback_context}\n\nQuestion: {message}"}
                            ],
                            temperature=0.4,
                            max_tokens=4000
                        )
                        answer = response.get("choices", [{}])[0].get("message", {}).get("content", None)
                        if answer:
                            return {
                                "success": True,
                                "response": answer.strip() + "\n\n(Note: Response based on limited context due to size constraints)",
                                "mode": "grok_mode_reduced"
                            }
                    except:
                        pass
            
            return {"success": False, "error": f"Grok Mode error: {str(e)}"}  # Ye return
    
    except Exception as e:  # Ye general except
        print("🔥 Grok Mode General Exception:", e)  # Ye print
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}  # Ye return

# ========== GROK MODE SUMMARY (Full Website) ==========
# Ye endpoint summary handle karta hai for full website
@app.post("/grok-summary")
async def grok_summary(request: Request):
    form = await request.form()  # Ye form
    scraped = form.get("scraped_data")  # Ye scraped
    
    if not scraped:  # Ye check
        return {"success": False, "error": "Missing scraped data"}  # Ye error
    if not groq_ai:  # Ye check
        return {"success": False, "error": "Groq AI client not initialized"}  # Ye error
    
    data = json.loads(scraped)  # Ye parse
    
    # Check if multi-page
    is_multi_page = "pages" in data and isinstance(data["pages"], list)
    
    if is_multi_page:
        # Full website summary
        pages = data["pages"]
        system_prompt = f"""You are GROK MODE SUMMARY - Create a comprehensive website summary.

This website has {len(pages)} pages. Create a structured summary covering:

1. WEBSITE OVERVIEW - Main purpose, topic, target audience
2. SITE STRUCTURE - How pages are organized, main sections
3. KEY PAGES SUMMARY - For each important page, what it contains
4. MAIN FINDINGS - Key information across the entire site
5. STATISTICS & DATA - Any numbers, facts, or data found
6. OVERALL CONCLUSION - Main takeaway from the whole website

Be thorough but concise. Use ALL pages to create a complete picture."""
        
        # Build context from all pages
        context_parts = [f"Website URL: {data.get('url', '')}"]
        context_parts.append(f"Total Pages: {len(pages)}")
        context_parts.append(f"Site Title: {data.get('title', '')}")
        context_parts.append("")
        
        for idx, page in enumerate(pages[:20]):  # Pehle 20 pages ka full context
            context_parts.append(f"--- PAGE {idx+1}: {page.get('title', 'No Title')} ---")
            context_parts.append(f"URL: {page.get('url', '')}")
            if page.get('description'):
                context_parts.append(f"Desc: {page['description']}")
            if page.get('paragraphs'):
                context_parts.append("Content:")
                context_parts.extend(page['paragraphs'][:5])  # Pehle 5 paragraphs
            context_parts.append("")
        
        if len(pages) > 20:
            context_parts.append(f"... and {len(pages) - 20} more pages")
        
        full_context = "\n".join(context_parts)
        
    else:
        # Single page summary (as before)
        system_prompt = """You are GROK MODE SUMMARY - Extract key facts instantly and accurately.

Provide a structured summary with:
1. MAIN TOPIC - What the page is about
2. KEY POINTS - 3-5 most important facts
3. STATISTICS - Any numbers/data found
4. CONCLUSION - Main takeaway

Only use data from the page. If info missing, say "Not found"."""
        
        context_parts = [f"URL: {data.get('url', '')}"]
        if data.get('title'):
            context_parts.append(f"Title: {data['title']}")
        if data.get('description'):
            context_parts.append(f"Description: {data['description']}")
        if data.get('paragraphs'):
            context_parts.append("\nContent:\n" + "\n".join(data['paragraphs'][:15]))
        
        full_context = "\n".join(context_parts)
    
    try:  # Ye try
        response = groq_ai.chat_completions_create(  # Ye call
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context[:50000]}  # Limit context
            ],
            temperature=0.1,
            max_tokens=2000
        )
        
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")  # Ye extract
        
        return {  # Ye return
            "success": True,
            "summary": answer.strip(),
            "mode": "grok_summary",
            "pages_count": len(pages) if is_multi_page else 1
        }
        
    except Exception as e:  # Ye except
        return {"success": False, "error": f"Summary error: {str(e)}"}  # Ye return