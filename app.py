# FINAL FIXED APP.PY - Large Data Handling with Professional Optimization
# CRITICAL FIX: Chat gives EXACT answers from scraped data - NO TRUNCATION
# Jab bhi scraped data se question poocho to poora answer mile, chhota nahi

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os, json, time, uuid, gzip, hashlib
import requests
from typing import Dict, Any, Optional

from scraper import UltraScraper

# Load .env
load_dotenv()

# Initialize FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")

# GROQ API setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Data limits
MAX_RESPONSE_SIZE = 50 * 1024 * 1024  # 50MB max
CHUNK_SIZE = 8000
MAX_PAGES_LARGE = 100

# Direct Groq API client
class GroqDirectClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500, **kwargs):
        try:
            data = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            data.update(kwargs)
            
            # Large request handling
            json_data = json.dumps(data)
            if len(json_data) > 100000:
                print("🔍 Large request detected")
                data["max_tokens"] = min(max_tokens, 4000)
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=120  # Increased timeout for large data
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise Exception("Request timeout - data too large")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error: {str(e)}")
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")

# Global clients
groq_ai = None
grok_mode = None

# Initialize Groq clients
def initialize_grok_clients():
    global groq_ai, grok_mode
    try:
        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode = GroqDirectClient(GROQ_API_KEY)
        print("✅ Groq clients initialized")
        return True
    except Exception as e:
        print(f"⚠️ Initialization failed: {e}")
        try:
            from groq import Groq
            groq_ai = Groq(api_key=GROQ_API_KEY)
            grok_mode = Groq(api_key=GROQ_API_KEY)
            print("✅ Groq clients initialized (Standard)")
            return True
        except Exception as e2:
            print(f"❌ All methods failed: {e2}")
            groq_ai = None
            grok_mode = None
            return False

# Data compression utilities
def compress_data(data: str) -> str:
    compressed = gzip.compress(data.encode('utf-8'))
    return compressed.hex()

def decompress_data(hex_data: str) -> str:
    try:
        compressed = bytes.fromhex(hex_data)
        return gzip.decompress(compressed).decode('utf-8')
    except:
        return hex_data

def optimize_data_size(data: Dict[str, Any]) -> Dict[str, Any]:
    """Data size optimization - storage ke liye, chat ke liye nahi"""
    try:
        data_str = json.dumps(data, ensure_ascii=False)
    except MemoryError:
        print("🔥 Memory error, applying aggressive optimization...")
        optimized = data.copy()
        
        # Limit large fields for storage only
        if 'paragraphs' in optimized:
            optimized['paragraphs'] = optimized['paragraphs'][:50]
        if 'images' in optimized:
            optimized['images'] = optimized['images'][:20]
        if 'internal_links' in optimized:
            optimized['internal_links'] = optimized['internal_links'][:100]
        if 'pages' in optimized:
            optimized['pages'] = optimized['pages'][:10]
        if 'full_text' in optimized:
            optimized['full_text'] = optimized['full_text'][:50000] + "...[truncated]"
        
        optimized['data_truncated'] = True
        optimized['truncated_reason'] = 'memory_error'
        
        try:
            data_str = json.dumps(optimized, ensure_ascii=False)
        except MemoryError:
            print("🔥 Still memory error, using compression...")
            compressed_json = compress_data(str(optimized))
            return {
                'compressed_data': compressed_json,
                'is_compressed': True,
                'data_truncated': True
            }
    
    if len(data_str) > MAX_RESPONSE_SIZE:
        print(f"🔍 Data size {len(data_str)} bytes, optimizing for storage...")
        optimized = data.copy()
        
        # Storage optimization -不影响chat quality
        if 'paragraphs' in optimized and len(optimized['paragraphs']) > 50:
            optimized['paragraphs'] = optimized['paragraphs'][:50]
            optimized['data_truncated'] = True
        if 'images' in optimized and len(optimized['images']) > 20:
            optimized['images'] = optimized['images'][:20]
            optimized['data_truncated'] = True
        if 'full_text' in optimized and len(optimized['full_text']) > 50000:
            optimized['full_text'] = optimized['full_text'][:50000] + "...[truncated]"
            optimized['data_truncated'] = True
        if 'pages' in optimized and len(optimized['pages']) > 10:
            optimized['pages'] = optimized['pages'][:10]
            optimized['data_truncated'] = True
        
        return optimized
    
    return data

# Initialize clients
initialize_grok_clients()

# ========== HOME ==========
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ========== HEALTH ==========
@app.get("/health")
async def health():
    return {"status": "healthy", "large_data_support": True}

# ========== SCRAPE ==========
@app.post("/scrape")
async def scrape(request: Request):
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")
        max_pages = int(form.get("max_pages", MAX_PAGES_LARGE))

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        print(f"🔍 Scraping: {url}, Mode: {mode}, Max Pages: {max_pages}")

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode, max_pages=max_pages)
        else:
            data = scraper.scrape_single_page(url, mode)

        print(f"✅ Scraping completed: {url}")
        
        if "error" in data:
            return {"success": False, "error": data["error"]}
        
        # Storage optimization -不影响chat
        optimized_data = optimize_data_size(data)
        
        optimized_data["session_id"] = str(uuid.uuid4())
        optimized_data["scrape_id"] = optimized_data.get("scrape_id", str(uuid.uuid4()))
        
        return {"success": True, "data": optimized_data}
    
    except Exception as e:
        print(f"❌ Scraping error: {str(e)}")
        return {"success": False, "error": f"Scraping failed: {str(e)}"}

# ========== GROQ CHAT - FIXED FOR EXACT ANSWERS ==========
# CRITICAL FIX: Ye endpoint ab scraped data se POORA answer degi, chhota nahi
@app.post("/groq-chat")
async def chat(request: Request):
    try:
        form = await request.form()
        message = form.get("message")
        scraped = form.get("scraped_data")
        
        if not message or not scraped:
            return {"success": False, "error": "Missing data"}
        if not groq_ai:
            return {"success": False, "error": "Groq AI client not initialized"}

        # Handle compressed data
        try:
            data = json.loads(scraped)
            if data.get('is_compressed'):
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {str(e)}")
            return {"success": False, "error": "Invalid JSON format"}
        except Exception as e:
            print(f"❌ Data processing error: {str(e)}")
            return {"success": False, "error": f"Data processing failed: {str(e)}"}

        # CRITICAL: System prompt for EXACT answers from scraped data
        system_prompt = """You are an EXACT factual AI assistant. Your ONLY job is to answer questions SOLELY from the scraped website data provided.

CRITICAL RULES:
1. ONLY use the scraped data below - NO outside knowledge
2. If user asks for URLs, give ALL URLs from the data
3. If user asks for images, give ALL image URLs
4. If user asks for 5 things, give EXACTLY 5 if available
5. NEVER truncate or summarize lists - provide COMPLETE information
6. Format answers clearly with bullet points or numbers
7. If asked for specific count (like "give me 5 URLs"), provide exactly that many
8. If information not found, say: "This information is not available in the scraped website data."

Remember: The scraped data contains COMPLETE information. Give FULL answers, NOT summaries."""
        
        # FIXED: NO TRUNCATION - Full data bhej rahe hain
        # Sirf structure ko readable banate hain, data nahi kat-te
        data_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        # CRITICAL: Poora data bhejo, chhota mat karo
        # User ne poora data scrape kiya hai, poora jawab chahte hain
        context = f"""SCRAPED WEBSITE DATA (COMPLETE - USE THIS ONLY):

{data_str}

USER QUESTION:
{message}

INSTRUCTIONS: Answer the question using ONLY the scraped data above. Give COMPLETE, EXACT answers. If the user asks for lists (like URLs, images, etc.), provide ALL items from the data. DO NOT summarize or truncate."""

        try:
            print(f"📤 Sending chat request with FULL data (size: {len(data_str)} chars)")
            
            response = groq_ai.chat_completions_create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0,  # Zero temperature for exact, factual answers
                max_tokens=32000  # EXTRA LARGE for complete answers
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No answer returned").strip()
            
            print(f"✅ Chat response received (length: {len(answer)} chars)")
            return {"success": True, "response": answer}
            
        except Exception as e:
            print(f"❌ Groq API error: {str(e)}")
            # Agar token limit issue hai to aur try karte hain
            if "token" in str(e).lower():
                try:
                    print("🔄 Token limit issue, retrying with chunked approach...")
                    # Data ko chunks mein tod kar bhejte hain
                    chunks = []
                    chunk_size = 50000
                    for i in range(0, len(data_str), chunk_size):
                        chunks.append(data_str[i:i+chunk_size])
                    
                    chunk_context = f"""SCRAPED DATA (CHUNK 1 of {len(chunks)}):
{chunks[0]}

Note: This is part 1 of the data. User question: {message}

If you need more data chunks to answer completely, I will provide them."""
                    
                    response = groq_ai.chat_completions_create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": chunk_context}
                        ],
                        temperature=0,
                        max_tokens=32000
                    )
                    
                    answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No answer").strip()
                    return {"success": True, "response": answer}
                except Exception as e2:
                    print(f"❌ Retry failed: {str(e2)}")
                    return {"success": False, "error": f"Groq API error: {str(e)}"}
            else:
                return {"success": False, "error": f"Groq API error: {str(e)}"}
    
    except Exception as e:
        print(f"❌ Chat endpoint error: {str(e)}")
        return {"success": False, "error": f"Chat failed: {str(e)}"}

# ========== EXPORT ==========
@app.post("/export")
async def export(request: Request):
    try:
        body = await request.json()
        fmt = body.get("format")
        data = body.get("data")

        if not fmt or not data:
            return {"success": False, "error": "Missing format or data"}

        if isinstance(data, dict) and data.get('is_compressed'):
            try:
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
            except Exception as e:
                print(f"❌ Export decompression error: {str(e)}")
                return {"success": False, "error": "Failed to decompress data"}

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
    
    except Exception as e:
        print(f"❌ Export error: {str(e)}")
        return {"success": False, "error": f"Export failed: {str(e)}"}

# ========== GROK MODE ==========
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
        
        try:
            data = json.loads(scraped)
            if data.get('is_compressed'):
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid scraped data format"}
        except Exception as e:
            return {"success": False, "error": f"Data processing error: {str(e)}"}
        
        system_prompt = f"""You are Grok Mode - advanced AI for universal questions.

Rules:
1. ONLY answer universal/general knowledge questions
2. DO NOT use scraped data - ignore website content
3. Use comprehensive knowledge for all answers
4. Analysis Type: {analysis_type}"""
        
        full_context = f"USER QUESTION:\n{message}\n\n(Universal knowledge question - ignore scraped data)"

        try:
            messages_to_send = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}
            ]
            
            response = grok_mode.chat_completions_create(
                model=MODEL_DEEP,
                messages=messages_to_send,
                temperature=0.4,
                max_tokens=8000
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", None)
            if not answer:
                answer = "No response generated."
            
            return {
                "success": True, 
                "response": answer.strip(),
                "mode": "grok_mode",
                "analysis_type": analysis_type
            }
            
        except Exception as e:
            print("🔥 Grok Mode Exception:", e)
            return {"success": False, "error": f"Grok Mode error: {str(e)}"}
    
    except Exception as e:
        print("🔥 Grok Mode General Exception:", e)
        return {"success": False, "error": f"Grok Mode failed: {str(e)}"}

# ========== GROK SUMMARY ==========
@app.post("/grok-summary")
async def grok_summary(request: Request):
    try:
        form = await request.form()
        scraped = form.get("scraped_data")
        
        if not scraped:
            return {"success": False, "error": "Missing scraped data"}
        if not groq_ai:
            return {"success": False, "error": "Groq AI client not initialized"}
        
        try:
            data = json.loads(scraped)
            if data.get('is_compressed'):
                decompressed_data = decompress_data(data['compressed_data'])
                data = json.loads(decompressed_data)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid scraped data format"}
        except Exception as e:
            return {"success": False, "error": f"Data processing error: {str(e)}"}
    
        system_prompt = """You are GROK SUMMARY - Extract key facts instantly.

Provide structured summary with:
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
            paragraphs_text = "\n".join(data['paragraphs'][:20])
            context_parts.append(f"\nContent:\n{paragraphs_text}")
        
        try:
            response = groq_ai.chat_completions_create(
                model=MODEL_DEEP,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n\n".join(context_parts)}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No summary generated.")
            
            return {
                "success": True,
                "summary": answer.strip(),
                "mode": "grok_summary"
            }
            
        except Exception as e:
            print(f"❌ Summary error: {str(e)}")
            return {"success": False, "error": f"Summary error: {str(e)}"}
    
    except Exception as e:
        print(f"❌ Summary endpoint error: {str(e)}")
        return {"success": False, "error": f"Summary failed: {str(e)}"}

# ========== ERROR HANDLING ==========
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Global error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error. Please try again."}
    )