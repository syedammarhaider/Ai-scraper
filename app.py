# FINAL FIXED APP.PY - Large Data Handling + Detailed Answers from Scraped Data
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os, json, time, uuid, gzip, hashlib
import requests
from typing import Dict, Any, Optional
from scraper import UltraScraper

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

app.mount("/static", StaticFiles(directory="static"), name="static")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

MAX_RESPONSE_SIZE = 50 * 1024 * 1024  # 50MB
CHUNK_SIZE = 8000
MAX_PAGES_LARGE = 100

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

            json_data = json.dumps(data)
            if len(json_data) > 100000:
                print("Large request → optimized params")
                data["max_tokens"] = min(max_tokens, 4000)

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=60
            )
            response.raise_for_status()
            
            # Parse JSON response with error handling
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                print(f"Response text: {response.text[:500]}")  # Log first 500 chars
                raise Exception(f"Invalid JSON response from API: {str(e)}")
            
            # Validate that result is a dictionary
            if not isinstance(result, dict):
                print(f"Invalid response type: {type(result)}")
                raise Exception(f"API response is not a dictionary: {type(result)}")
            
            return result
            
        except requests.exceptions.Timeout:
            raise Exception("Request timeout - data too large or server slow")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error: {str(e)}")
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")

groq_ai = None
grok_mode = None

def initialize_grok_clients():
    global groq_ai, grok_mode
    try:
        groq_ai = GroqDirectClient(GROQ_API_KEY)
        grok_mode = GroqDirectClient(GROQ_API_KEY)
        print("Groq clients initialized (Direct)")
        return True
    except Exception as e:
        print(f"Direct init failed: {e}")
        try:
            from groq import Groq
            groq_ai = Groq(api_key=GROQ_API_KEY)
            grok_mode = Groq(api_key=GROQ_API_KEY)
            print("Groq clients initialized (SDK)")
            return True
        except Exception as e2:
            print(f"All init failed: {e2}")
            return False

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
    # Aggressive truncation + compression if data is very large
    try:
        data_str = json.dumps(data, ensure_ascii=False)
    except MemoryError:
        print("Memory error → aggressive truncate")
        optimized = data.copy()
        for k in ['paragraphs', 'images', 'internal_links', 'external_links', 'pages']:
            if k in optimized and isinstance(optimized[k], list):
                optimized[k] = optimized[k][:30]
        if 'full_text' in optimized:
            optimized['full_text'] = optimized['full_text'][:80000] + "...[truncated]"
        optimized['data_truncated'] = True
        try:
            data_str = json.dumps(optimized, ensure_ascii=False)
        except MemoryError:
            print("Still memory error → compression")
            return {
                'compressed_data': compress_data(str(optimized)),
                'is_compressed': True,
                'data_truncated': True
            }

    if len(data_str) > MAX_RESPONSE_SIZE:
        print(f"Data too large ({len(data_str)} bytes) → optimizing")
        optimized = data.copy()
        for k in ['paragraphs', 'images', 'internal_links', 'external_links']:
            if k in optimized and isinstance(optimized[k], list) and len(optimized[k]) > 80:
                optimized[k] = optimized[k][:80]
        if 'full_text' in optimized and len(optimized['full_text']) > 80000:
            optimized['full_text'] = optimized['full_text'][:80000] + "..."
        if 'pages' in optimized and len(optimized['pages']) > 15:
            optimized['pages'] = optimized['pages'][:15]

        try:
            final_size = len(json.dumps(optimized, ensure_ascii=False))
        except:
            print("Final size check failed → compression")
            optimized = {
                'compressed_data': compress_data(json.dumps(optimized, separators=(',', ':'))),
                'is_compressed': True,
                'data_truncated': True
            }
            for k in ['paragraphs','images','links','full_text','pages','structured_data']:
                optimized.pop(k, None)
            return optimized

        if final_size > MAX_RESPONSE_SIZE:
            print("Still too large → compression + field removal")
            compressed = compress_data(json.dumps(optimized, separators=(',', ':')))
            optimized = {
                'compressed_data': compressed,
                'is_compressed': True,
                'data_truncated': True
            }
            for k in ['paragraphs','images','internal_links','external_links','full_text','pages','structured_data']:
                optimized.pop(k, None)

    return optimized if 'optimized' in locals() else data

initialize_grok_clients()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "healthy", "large_data_support": True}

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

        print(f"Scraping: {url} | mode: {mode} | max_pages: {max_pages}")

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode, max_pages=max_pages)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        optimized = optimize_data_size(data)
        optimized["session_id"] = str(uuid.uuid4())
        optimized["scrape_id"] = optimized.get("scrape_id", str(uuid.uuid4()))

        return {"success": True, "data": optimized}

    except Exception as e:
        print(f"Scrape error: {str(e)}")
        return {"success": False, "error": str(e)}

@app.post("/groq-chat")
async def chat(request: Request):
    try:
        form = await request.form()
        message = form.get("message")
        scraped = form.get("scraped_data")

        if not message or not scraped:
            return {"success": False, "error": "Missing message or scraped_data"}

        if not groq_ai:
            return {"success": False, "error": "Groq client not ready"}

        # Decompress if needed
        try:
            data = json.loads(scraped)
            if data.get('is_compressed'):
                data = json.loads(decompress_data(data['compressed_data']))
        except Exception as e:
            print(f"Data parse/decompress error: {e}")
            return {"success": False, "error": "Invalid or corrupted scraped data"}

        # ──────────────────────────────────────────────
        # Most important change → force detailed & complete answers
        system_prompt = """You are an EXACT and COMPLETE factual assistant.
You MUST follow these strict rules:

1. Answer ONLY using the provided SCRAPED DATA. Never guess, never use outside knowledge.
2. Be extremely detailed and thorough — give FULL lists when asked (all URLs, all images, all links, etc.).
3. If user asks for "all", "list", "every", "complete", "full", "top 10", "how many" → give complete answer, do NOT summarize or shorten.
4. If user asks for specific number (give me 5 links, top 8 images) → give exactly that many, do NOT give less.
5. If list is very long → still try to include as much as possible, do NOT say "many" or cut arbitrarily.
6. If information is not in the data → say exactly: "This information is not available in the scraped website data."
7. Format lists clearly using markdown (bullet points or numbered).
8. For greetings → respond naturally but briefly.

Never be brief when user wants details or lists.
"""
        # ──────────────────────────────────────────────

        # Try to send as much context as possible
        try:
            data_json = json.dumps(data, ensure_ascii=False, indent=2)
            if len(data_json) > 28000:
                context = data_json[:28000] + "\n\n[Note: data is truncated due to length — but most important fields are included]"
            else:
                context = data_json
        except:
            context = str(data)[:28000] + "... [data stringified]"

        full_user_content = f"""SCRAPED DATA:\n{context}\n\nUSER QUESTION:\n{message}"""

        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": full_user_content}
            ],
            temperature=0.1,           # low → more deterministic & exact
            max_tokens=4096            # increased → allow long lists & detailed answers
        )

        # Carefully validate response structure to avoid 'dict' object has no attribute 'choices' error
        if not isinstance(response, dict):
            print(f"Invalid response type: {type(response)}")
            return {"success": False, "error": "Invalid API response format"}
        
        if "choices" not in response:
            print(f"Response missing 'choices' key: {response}")
            return {"success": False, "error": "API response missing choices"}
        
        if not isinstance(response["choices"], list) or len(response["choices"]) == 0:
            print(f"Invalid choices format: {response['choices']}")
            return {"success": False, "error": "No choices in API response"}
        
        first_choice = response["choices"][0]
        if not isinstance(first_choice, dict) or "message" not in first_choice:
            print(f"Invalid choice format: {first_choice}")
            return {"success": False, "error": "Invalid choice format in API response"}
        
        message = first_choice["message"]
        if not isinstance(message, dict) or "content" not in message:
            print(f"Invalid message format: {message}")
            return {"success": False, "error": "Invalid message format in API response"}
        
        answer = message["content"]
        if not isinstance(answer, str):
            answer = str(answer)
        
        answer = answer.strip()
        if not answer:
            answer = "No answer returned from API"

        return {"success": True, "response": answer}

    except Exception as e:
        print(f"Chat error: {str(e)}")
        return {"success": False, "error": f"Chat failed: {str(e)}"}

# ──────────────────────────────────────────────
# The rest of the endpoints remain unchanged
# ──────────────────────────────────────────────

@app.post("/export")
async def export(request: Request):
    try:
        body = await request.json()
        fmt = body.get("format")
        data = body.get("data")

        if not fmt or not data:
            return {"success": False, "error": "Missing format or data"}

        if isinstance(data, dict) and data.get('is_compressed'):
            data = json.loads(decompress_data(data['compressed_data']))

        filename = f"scraped_data_{int(time.time())}"
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
        print(f"Export error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/grok-mode")
async def grok_mode_endpoint(request: Request):
    # unchanged - universal knowledge mode
    try:
        form = await request.form()
        message = form.get("message")
        scraped = form.get("scraped_data")  # ignored anyway
        analysis_type = form.get("analysis_type", "comprehensive")

        if not message:
            return {"success": False, "error": "Message required"}

        if not grok_mode:
            return {"success": False, "error": "Grok client not ready"}

        system_prompt = f"""You are Grok Mode - advanced universal knowledge assistant.
Rules:
- ONLY answer general/universal questions
- IGNORE any scraped/website data
- Use your full knowledge
- Be detailed & comprehensive
- Analysis type: {analysis_type}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": message}
        ]

        resp = grok_mode.chat_completions_create(
            model=MODEL_DEEP,
            messages=messages,
            temperature=0.4,
            max_tokens=8000
        )

        # Validate response structure to avoid 'dict' object has no attribute 'choices' error
        if not isinstance(resp, dict) or "choices" not in resp:
            return {"success": False, "error": "Invalid API response format"}
        
        if not isinstance(resp["choices"], list) or len(resp["choices"]) == 0:
            return {"success": False, "error": "No choices in API response"}
        
        first_choice = resp["choices"][0]
        if not isinstance(first_choice, dict) or "message" not in first_choice:
            return {"success": False, "error": "Invalid choice format in API response"}
        
        message = first_choice["message"]
        if not isinstance(message, dict) or "content" not in message:
            return {"success": False, "error": "Invalid message format in API response"}
        
        answer = message["content"].strip() if isinstance(message["content"], str) else str(message["content"]).strip()
        if not answer:
            answer = "No response"

        return {
            "success": True,
            "response": answer,
            "mode": "grok_mode",
            "model": MODEL_DEEP
        }

    except Exception as e:
        print(f"Grok mode error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/grok-summary")
async def grok_summary(request: Request):
    # unchanged - summary mode
    try:
        form = await request.form()
        scraped = form.get("scraped_data")

        if not scraped:
            return {"success": False, "error": "Missing scraped_data"}

        if not groq_ai:
            return {"success": False, "error": "Groq client not ready"}

        data = json.loads(scraped)
        if data.get('is_compressed'):
            data = json.loads(decompress_data(data['compressed_data']))

        system_prompt = """You are GROK SUMMARY - create concise structured summary.
Always include:
- MAIN TOPIC
- KEY POINTS (3-5)
- STATISTICS (if any)
- CONCLUSION
Use only provided data. Say "Not found" when missing."""

        context_parts = []
        for k in ['url','title','description']:
            if data.get(k):
                context_parts.append(f"{k.title()}: {data[k]}")

        if data.get('paragraphs'):
            paragraphs_text = "\n".join(data['paragraphs'][:25])
            context_parts.append(f"Content:\n{paragraphs_text}")

        resp = groq_ai.chat_completions_create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": "\n\n".join(context_parts)}
            ],
            temperature=0.1,
            max_tokens=1200
        )

        # Validate response structure to avoid 'dict' object has no attribute 'choices' error
        if not isinstance(resp, dict) or "choices" not in resp:
            return {"success": False, "error": "Invalid API response format"}
        
        if not isinstance(resp["choices"], list) or len(resp["choices"]) == 0:
            return {"success": False, "error": "No choices in API response"}
        
        first_choice = resp["choices"][0]
        if not isinstance(first_choice, dict) or "message" not in first_choice:
            return {"success": False, "error": "Invalid choice format in API response"}
        
        message = first_choice["message"]
        if not isinstance(message, dict) or "content" not in message:
            return {"success": False, "error": "Invalid message format in API response"}
        
        summary = message["content"].strip() if isinstance(message["content"], str) else str(message["content"]).strip()
        if not summary:
            summary = "No summary"

        return {
            "success": True,
            "summary": summary,
            "mode": "grok_summary"
        }

    except Exception as e:
        print(f"Summary error: {e}")
        return {"success": False, "error": str(e)}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Global error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Server error. Try again."}
    )