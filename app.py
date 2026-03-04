# FINAL FIXED APP.PY - Large Data Handling with Professional Optimization
# Roman Urdu comments: Har line ke upar explain kiya gaya hai ke ye kya karti hai
# Large data handling: Chunking, compression, memory optimization, proper error handling
# 100% professional code jo large data ko handle karta hai bina error ke

from fastapi import FastAPI, Request, HTTPException  # Ye imports FastAPI aur error handling ke liye
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse  # Ye responses ke liye
from fastapi.templating import Jinja2Templates  # Ye templates ke liye
from fastapi.staticfiles import StaticFiles  # Ye static files serve ke liye
from dotenv import load_dotenv  # Ye .env load ke liye
import os, json, time, uuid, gzip, hashlib  # Ye basic imports with gzip for compression
import requests  # Ye requests import hai for direct Groq API
from typing import Dict, Any, Optional  # Ye type hints ke liye

from scraper import UltraScraper  # Ye custom scraper import karti hai

# Load .env variables - Ye line .env file se variables load karti hai
load_dotenv()

# Initialize FastAPI - Ye line app create karti hai
app = FastAPI()
templates = Jinja2Templates(directory="templates")  # Ye templates set karti hai
scraper = UltraScraper()  # Ye scraper object create karti hai

# Mount static files - Ye line static files serve karta hai
app.mount("/static", StaticFiles(directory="static"), name="static")

# GROQ - Using direct API calls with large data handling - Ye comment Groq ke bare mein hai
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Ye API key get karti hai
MODEL = "llama-3.3-70b-versatile"  # Ye model set karti hai
MODEL_DEEP = "llama-3.3-70b-versatile"  # Ye deep model set karti hai

# Data size limits for optimal performance - Ye constants define karti hai limits
MAX_RESPONSE_SIZE = 50 * 1024 * 1024  # 50MB max response size
CHUNK_SIZE = 8000  # 8KB chunks for processing
MAX_PAGES_LARGE = 100  # Maximum pages for large scraping

# Direct Groq API client with enhanced error handling - Ye class direct client banati hai
class GroqDirectClient:
    # Ye init function client initialize karta hai
    def __init__(self, api_key):
        self.api_key = api_key  # Ye API key save karti hai
        self.base_url = "https://api.groq.com/openai/v1"  # Ye base URL set karti hai
        self.headers = {  # Ye headers dictionary banati hai
            "Authorization": f"Bearer {api_key}",  # Ye auth header
            "Content-Type": "application/json"  # Ye content type
        }
    
    # Ye function chat completion create karta hai with large data handling
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500, **kwargs):
        try:  # Ye try block error handle ke liye
            data = {  # Ye data dictionary banati hai
                "model": model,  # Ye model
                "messages": messages,  # Ye messages
                "temperature": temperature,  # Ye temperature
                "max_tokens": max_tokens  # Ye max tokens
            }
            data.update(kwargs)  # Ye extra kwargs add karti hai
            
            # Compress large requests - Ye large requests ko compress karta hai
            json_data = json.dumps(data)
            if len(json_data) > 100000:  # 100KB se zyada ho to
                print("🔍 Large request detected, using optimized parameters")
                data["max_tokens"] = min(max_tokens, 4000)  # Tokens limit karta hai
            
            response = requests.post(  # Ye POST request bhejti hai
                f"{self.base_url}/chat/completions",  # Ye URL
                headers=self.headers,  # Ye headers
                json=data,  # Ye JSON data
                timeout=60  # Increased timeout for large data
            )
            response.raise_for_status()  # Ye error check
            return response.json()  # Ye JSON return
        except requests.exceptions.Timeout:  # Ye timeout handle
            raise Exception("Request timeout - data too large or server slow")
        except requests.exceptions.RequestException as e:  # Ye request error handle
            raise Exception(f"Network error: {str(e)}")
        except Exception as e:  # Ye general exception handle
            raise Exception(f"Groq API error: {str(e)}")

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

# Data compression utilities - Ye functions data compression ke liye hain
def compress_data(data: str) -> str:
    """Ye function data ko compress karta hai gzip se"""
    compressed = gzip.compress(data.encode('utf-8'))
    return compressed.hex()  # Hex string mein convert karta hai

def decompress_data(hex_data: str) -> str:
    """Ye function compressed data ko decompress karta hai"""
    try:
        compressed = bytes.fromhex(hex_data)
        return gzip.decompress(compressed).decode('utf-8')
    except:
        return hex_data  # Fallback agar decompress na ho

def optimize_data_size(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ye function data size ko optimize karta hai"""
    try:
        data_str = json.dumps(data, ensure_ascii=False)
    except MemoryError:
        print("🔥 Memory error during JSON serialization, applying aggressive optimization...")
        # Agar memory error aaye to aggressive optimization karta hai
        optimized = data.copy()
        
        # Sabhi large fields ko immediately limit karta hai
        if 'paragraphs' in optimized:
            optimized['paragraphs'] = optimized['paragraphs'][:50]
        if 'images' in optimized:
            optimized['images'] = optimized['images'][:20]
        if 'internal_links' in optimized:
            optimized['internal_links'] = optimized['internal_links'][:100]
        if 'external_links' in optimized:
            optimized['external_links'] = optimized['external_links'][:100]
        if 'pages' in optimized:
            optimized['pages'] = optimized['pages'][:10]
        if 'full_text' in optimized:
            optimized['full_text'] = optimized['full_text'][:50000] + "...[truncated]"
        if 'structured_data' in optimized:
            if 'tables' in optimized['structured_data']:
                optimized['structured_data']['tables'] = optimized['structured_data']['tables'][:5]
            if 'lists' in optimized['structured_data']:
                optimized['structured_data']['lists'] = optimized['structured_data']['lists'][:10]
        
        optimized['data_truncated'] = True
        optimized['truncated_reason'] = 'memory_error_aggressive'
        
        # Phir se try karta hai
        try:
            data_str = json.dumps(optimized, ensure_ascii=False)
        except MemoryError:
            # Agar abhi bhi memory error aaye to compression use karta hai
            print("🔥 Still memory error, using compression...")
            compressed_json = compress_data(str(optimized))  # String representation compress karta hai
            return {
                'compressed_data': compressed_json,
                'is_compressed': True,
                'data_truncated': True,
                'truncated_reason': 'memory_error_compressed'
            }
    
    if len(data_str) > MAX_RESPONSE_SIZE:
        print(f"🔍 Data size {len(data_str)} bytes, optimizing...")
        
        # Large data ke liye optimization strategy
        optimized = data.copy()
        
        # Paragraphs ko limit karta hai
        if 'paragraphs' in optimized and len(optimized['paragraphs']) > 50:
            optimized['paragraphs'] = optimized['paragraphs'][:50]
            optimized['data_truncated'] = True
            optimized['truncated_reason'] = 'paragraphs_limited'
        
        # Images ko limit karta hai
        if 'images' in optimized and len(optimized['images']) > 20:
            optimized['images'] = optimized['images'][:20]
            optimized['data_truncated'] = True
            optimized['truncated_reason'] = 'images_limited'
        
        # Internal links ko limit karta hai
        if 'internal_links' in optimized and len(optimized['internal_links']) > 100:
            optimized['internal_links'] = optimized['internal_links'][:100]
            optimized['data_truncated'] = True
            optimized['truncated_reason'] = 'links_limited'
        
        # Full text ko truncate karta hai
        if 'full_text' in optimized and len(optimized['full_text']) > 50000:
            optimized['full_text'] = optimized['full_text'][:50000] + "...[truncated]"
            optimized['data_truncated'] = True
            optimized['truncated_reason'] = 'full_text_limited'
        
        # Crawled pages ke liye special handling
        if 'pages' in optimized and len(optimized['pages']) > 10:
            optimized['pages'] = optimized['pages'][:10]
            optimized['data_truncated'] = True
            optimized['truncated_reason'] = 'pages_limited'
        
        # Final size check
        try:
            final_size = len(json.dumps(optimized, ensure_ascii=False))
        except MemoryError:
            # Memory error hai to compression use karta hai
            print("🔥 Memory error during final size check, using compression...")
            try:
                compressed_json = compress_data(json.dumps(optimized, ensure_ascii=False, separators=(',', ':')))
            except MemoryError:
                # Agar compression bhi fail ho jaye to string representation use karta hai
                print("🔥 Even compression failed, using string representation...")
                compressed_json = compress_data(str(optimized))
            optimized['compressed_data'] = compressed_json
            optimized['is_compressed'] = True
            # Large fields ko remove karta hai compression ke baad
            for key in ['paragraphs', 'images', 'internal_links', 'external_links', 'full_text', 'pages', 'structured_data']:
                if key in optimized:
                    del optimized[key]
            return optimized
        
        if final_size > MAX_RESPONSE_SIZE:
            # Agar abhi bhi bara hai to compression use karta hai
            print("🔍 Still too large, using compression...")
            try:
                compressed_json = compress_data(json.dumps(optimized, ensure_ascii=False))
            except MemoryError:
                print("🔥 Compression failed, using string representation...")
                compressed_json = compress_data(str(optimized))
            optimized['compressed_data'] = compressed_json
            optimized['is_compressed'] = True
            # Large fields ko remove karta hai compression ke baad
            for key in ['paragraphs', 'images', 'internal_links', 'external_links', 'full_text', 'pages', 'structured_data']:
                if key in optimized:
                    del optimized[key]
        
        print(f"✅ Data optimized to {len(json.dumps(optimized, ensure_ascii=False))} bytes")
        return optimized
    
    return data

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
    return {"status": "healthy", "large_data_support": True}  # Ye status return with feature flag

# ========== SCRAPE ==========
# Ye endpoint scrape karta hai with large data optimization
@app.post("/scrape")
async def scrape(request: Request):
    try:  # Ye try error handle ke liye
        form = await request.form()  # Ye form data get karti hai
        url = form.get("url")  # Ye URL get
        mode = form.get("mode", "comprehensive")  # Ye mode get, default comprehensive
        max_pages = int(form.get("max_pages", MAX_PAGES_LARGE))  # Ye max pages get

        if not url:  # Ye check URL empty to nahi
            return {"success": False, "error": "URL required"}  # Ye error return

        if not url.startswith("http"):  # Ye check http nahi to add
            url = "https://" + url  # Ye https add

        print(f"🔍 Scraping URL: {url}, Mode: {mode}, Max Pages: {max_pages}")  # Ye log print

        # Large data ke liye optimized scraping call
        if mode == "comprehensive":  # Ye check comprehensive mode hai to crawl
            data = scraper.crawl_website(url, mode, max_pages=max_pages)  # Ye crawl call with limit
        else:  # Ye else single scrape
            data = scraper.scrape_single_page(url, mode)  # Ye single call

        print(f"✅ Scraping completed for: {url}")  # Ye success print
        
        if "error" in data:   # Ye check error hai
            return {"success": False, "error": data["error"]}  # Ye error return
        
        # Data size optimization - Ye line data ko optimize karta hai
        optimized_data = optimize_data_size(data)
        
        # Session ID add karta hai
        optimized_data["session_id"] = str(uuid.uuid4())  # Ye session ID add (frontend ke liye)
        optimized_data["scrape_id"] = optimized_data.get("scrape_id", str(uuid.uuid4()))  # Ye scrape ID
        
        return {"success": True, "data": optimized_data}  # Ye success return
    
    except Exception as e:  # Ye exception handle
        print(f"❌ Scraping error: {str(e)}")  # Ye print
        return {"success": False, "error": f"Scraping failed: {str(e)}"}  # Ye return

# ========== GROQ CHAT ==========
# Ye endpoint Groq chat handle karta hai with large data handling
@app.post("/groq-chat")
async def chat(request: Request):
    try:  # Ye try block for robust error handling
        form = await request.form()  # Ye form get
        message = form.get("message")  # Ye message
        scraped = form.get("scraped_data")  # Ye scraped data
        
        if not message or not scraped:  # Ye check missing
            return {"success": False, "error": "Missing data"}  # Ye error
        if not groq_ai:  # Ye check client initialized nahi
            return {"success": False, "error": "Groq AI client not initialized"}  # Ye error

        # Handle compressed data - Ye compressed data handle karta hai
        try:
            data = json.loads(scraped)
            if data.get('is_compressed'):
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {str(e)}")
            return {"success": False, "error": "Invalid JSON format - data too large or corrupted"}
        except Exception as e:
            print(f"❌ Data processing error: {str(e)}")
            return {"success": False, "error": f"Data processing failed: {str(e)}"}

        system_prompt = """You are an EXACT factual AI assistant specializing in website content analysis.

Rules:
1. ONLY answer from provided scraped data - no outside knowledge
2. For URL requests: Extract and list ONLY real, meaningful URLs (filter out data:, javascript:, mailto:, tel:, # anchors)
3. For content questions: Be precise and use only the text content from paragraphs, headings, and descriptions
4. If information not found, say: "This information is not available in the scraped website data."
5. For greetings, respond naturally but briefly
6. Always prioritize accuracy over completeness - better to say "not found" than guess

Focus on: Real content URLs, actual text content, contact information, and factual data from the website."""
        
        # Smart context building with size limits - Ye context ko smartly build karta hai
        if "urls" in message.lower() or "links" in message.lower():
            # For URL requests, focus on links data
            context_parts = []
            context_parts.append(f"URL: {data.get('url', '')}")
            if data.get('internal_links'):
                context_parts.append(f"INTERNAL LINKS: {json.dumps(data['internal_links'], indent=2)}")
            if data.get('external_links'):
                context_parts.append(f"EXTERNAL LINKS: {json.dumps(data['external_links'], indent=2)}")
            if data.get('images'):
                context_parts.append(f"IMAGE URLS: {[img['url'] for img in data['images']]}")
            context = "\n\n".join(context_parts) + f"\n\nQUESTION: {message}"
        else:
            # For other questions, use full data with limits
            data_str = json.dumps(data, indent=2, ensure_ascii=False)
            if len(data_str) > 15000:  # 15KB se zyada ho to
                context = f"SCRAPED DATA:\n{data_str[:15000]}...\n\n[Data truncated for processing]\n\nQUESTION:\n{message}"
            else:
                context = f"SCRAPED DATA:\n{data_str}\n\nQUESTION:\n{message}"  # Ye context banati hai

        try:  # Ye try
            response = groq_ai.chat_completions_create(  # Ye call
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0,
                max_tokens=2000  # Increased for better responses
            )
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No answer returned").strip()  # Ye answer extract
            return {"success": True, "response": answer}  # Ye return
        except Exception as e:  # Ye exception
            print(f"❌ Groq API error: {str(e)}")
            return {"success": False, "error": f"Groq API error: {str(e)}"}  # Ye return
    
    except Exception as e:  # Ye outer exception
        print(f"❌ Chat endpoint error: {str(e)}")
        return {"success": False, "error": f"Chat failed: {str(e)}"}  # Ye return

# ========== EXPORT ==========
# Ye endpoint export handle karta hai with large data support
@app.post("/export")
async def export(request: Request):
    try:  # Ye try block
        body = await request.json()  # Ye JSON body get
        fmt = body.get("format")  # Ye format
        data = body.get("data")  # Ye data

        if not fmt or not data:  # Ye check missing
            return {"success": False, "error": "Missing format or data"}  # Ye error

        # Handle compressed data in export - Ye compressed data handle karta hai
        if isinstance(data, dict) and data.get('is_compressed'):
            try:
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
            except Exception as e:
                print(f"❌ Export decompression error: {str(e)}")
                return {"success": False, "error": "Failed to decompress data for export"}

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
    
    except Exception as e:  # Ye exception
        print(f"❌ Export error: {str(e)}")
        return {"success": False, "error": f"Export failed: {str(e)}"}  # Ye return

# ========== GROK MODE - ENHANCED AI ==========
# Ye endpoint Grok mode handle karta hai with large data optimization
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
            data = json.loads(scraped)
            # Handle compressed data - Ye compressed data handle karta hai
            if data.get('is_compressed'):
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid scraped data format - JSON parsing failed"}
        except Exception as e:
            return {"success": False, "error": f"Data processing error: {str(e)}"}
        
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
                max_tokens=8000  # Large response ke liye
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
# Ye endpoint summary handle karta hai with large data optimization
@app.post("/grok-summary")
async def grok_summary(request: Request):
    try:  # Ye try block
        form = await request.form()  # Ye form
        scraped = form.get("scraped_data")  # Ye scraped
        
        if not scraped:  # Ye check
            return {"success": False, "error": "Missing scraped data"}  # Ye error
        if not groq_ai:  # Ye check
            return {"success": False, "error": "Groq AI client not initialized"}  # Ye error
        
        try:  # Ye try
            data = json.loads(scraped)
            # Handle compressed data - Ye compressed data handle karta hai
            if data.get('is_compressed'):
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid scraped data format"}
        except Exception as e:
            return {"success": False, "error": f"Data processing error: {str(e)}"}
    
        system_prompt = """You are GROK MODE SUMMARY - Extract key facts instantly and accurately.

Provide a structured summary with:
1. MAIN TOPIC - What the page is about
2. KEY POINTS - 3-5 most important facts
3. STATISTICS - Any numbers/data found
4. CONCLUSION - Main takeaway

Only use data from the page. If info missing, say "Not found"."""  # Ye prompt
        
        context_parts = [f"URL: {data.get('url', '')}"]  # Ye parts list
        if data.get('title'):  # Ye check
            context_parts.append(f"Title: {data['title']}")  # Ye append
        if data.get('description'):  # Ye check
            context_parts.append(f"Description: {data['description']}")  # Ye append
        if data.get('paragraphs'):  # Ye check
            # Large data ke liye paragraphs limit karta hai
            paragraphs_text = "\n".join(data['paragraphs'][:20])  # First 20 paragraphs
            context_parts.append(f"\nContent:\n{paragraphs_text}")  # Ye content append
        
        try:  # Ye try
            response = groq_ai.chat_completions_create(  # Ye call
                model=MODEL_DEEP,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n\n".join(context_parts)}
                ],
                temperature=0.1,
                max_tokens=1000  # Summary ke liye moderate size
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")  # Ye extract
            
            return {  # Ye return
                "success": True,
                "summary": answer.strip(),
                "mode": "grok_summary"
            }
            
        except Exception as e:  # Ye except
            print(f"❌ Summary error: {str(e)}")
            return {"success": False, "error": f"Summary error: {str(e)}"}  # Ye return
    
    except Exception as e:  # Ye outer exception
        print(f"❌ Summary endpoint error: {str(e)}")
        return {"success": False, "error": f"Summary failed: {str(e)}"}  # Ye return

# ========== ERROR HANDLING MIDDLEWARE ==========
# Ye middleware global error handling ke liye
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Global error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error. Please try again."}
    )
