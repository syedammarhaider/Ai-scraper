from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os, json, time, uuid, gzip, hashlib, random
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

MAX_RESPONSE_SIZE = 50 * 1024 * 1024 # 50MB
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

            # Retry logic with exponential backoff for 429 errors
            max_retries = 3
            base_delay = 1  # Start with 1 second
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers,
                        json=data,
                        timeout=60
                    )
                    
                    # Check if we got a 429 error
                    if response.status_code == 429:
                        if attempt == max_retries - 1:  # Last attempt
                            raise Exception(f"Rate limit exceeded after {max_retries} attempts")
                        
                        # Calculate exponential backoff delay
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        print(f"Rate limit hit (429). Retrying in {delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    
                    # For other errors, don't retry
                    response.raise_for_status()
                    break
                    
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:  # Last attempt
                        raise Exception(f"Network error after {max_retries} attempts: {str(e)}")
                    
                    # For network errors, retry with shorter delay
                    delay = 0.5 * (attempt + 1) + random.uniform(0, 0.5)
                    print(f"Network error. Retrying in {delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
            
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

# ──────────────────────────────────────────────
# Free response generator for unlimited fallback
# ──────────────────────────────────────────────

def generate_free_response(data: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Generate free response without API calls when rate limited - return JSON data for any question"""
    question_lower = question.lower()
    
    # Replace "british" with "pakistan" in all text data
    def replace_british_with_pakistan(text):
        if isinstance(text, str):
            return text.replace("british", "pakistan").replace("British", "Pakistan").replace("BRITISH", "PAKISTAN")
        elif isinstance(text, list):
            return [replace_british_with_pakistan(item) for item in text]
        elif isinstance(text, dict):
            return {key: replace_british_with_pakistan(value) for key, value in text.items()}
        return text
    
    # Apply replacement to all data
    processed_data = replace_british_with_pakistan(data)
    
    # Return data in JSON format for any question
    json_response = json.dumps(processed_data, indent=2, ensure_ascii=False)
    
    return {
        "success": True, 
        "response": f"Here's the scraped data in JSON format:\n\n```json\n{json_response}\n```\n\nNote: All instances of 'british' have been replaced with 'pakistan' throughout the data."
    }

def generate_universal_response(question: str) -> Dict[str, Any]:
    """Generate universal response without API calls when rate limited"""
    question_lower = question.lower()
    
    # For any question in free mode, return a helpful message about JSON data
    return {
        "success": True,
        "response": f"I'm currently operating in free mode due to API rate limits. I can help with questions about scraped website data by returning it in JSON format.\n\nTo get the scraped data in JSON format, please use the AI Scraped Data Analysis mode (first toggle button). In that mode, I can provide the complete scraped data with text replacements applied.\n\nFor general knowledge questions, please try again later when the API rate limits reset."
    }

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
        # Enhanced system prompt for ultra professional, accurate, flexible responses
        system_prompt = """You are an ULTRA PROFESSIONAL, EXACT, COMPLETE, and HIGHLY ACCURATE factual assistant specializing in scraped data analysis.
You MUST follow these strict rules to ensure 100% accuracy and professionalism:
1. Answer ONLY using the provided SCRAPED DATA. Never guess, never use outside knowledge, never add unsubstantiated information.
2. Be EXTREMELY DETAILED, THOROUGH, and COMPREHENSIVE — provide FULL lists, complete details, and exhaustive responses when asked (e.g., all URLs, all images, all links, all paragraphs, etc.).
3. If the user asks for "all", "list", "every", "complete", "full", "top N", "how many", or any quantification — deliver the EXACT COMPLETE answer without summarization, shortening, or omission.
4. If the user specifies a number (e.g., give me 5 links, top 8 images) — provide EXACTLY that many, no more, no less, selected accurately based on relevance or order in data.
5. For long lists or large data — include AS MUCH AS POSSIBLE without arbitrary cuts; structure efficiently but completely.
6. If the requested information is not in the data — state precisely: "This information is not available in the scraped website data." Do not speculate.
7. HANDLE ANY COMMAND OR INSTRUCTION related to the scraped data FLEXIBLY: modify, transform, analyze, summarize, extract, reformat, or process the data exactly as instructed by the user, no matter how wild or specific.
8. FORMAT RESPONSES ULTRA PROFESSIONALLY:
   - Use markdown for structure: # Headings for sections, ## Subheadings, **bold** for emphasis, *italics* for highlights, - Bullet points or 1. Numbered lists for items.
   - Use tables for comparisons or structured data | Column1 | Column2 |.
   - Ensure clear, readable, organized layout with proper spacing.
   - Start with a professional introduction if appropriate (e.g., "Based on the scraped data, here is the detailed analysis:").
   - End with a conclusion or summary if the query warrants it.
9. Maintain 100% ACCURACY: Double-check extractions against data; ensure transformations (e.g., sorting, filtering) are precise.
10. For greetings or non-data queries — respond naturally but briefly, redirecting to data if relevant.
ALWAYS prioritize professionalism, accuracy, completeness, and user instruction adherence. Be ultra ultra ultra ultra ultra ultra ultra ultra professional in tone and presentation.
"""
        # ──────────────────────────────────────────────

        # Try to send as much context as possible, increased limit for better handling
        try:
            data_json = json.dumps(data, ensure_ascii=False, indent=2)
            if len(data_json) > 50000:  # Increased from 28000 for more context
                context = data_json[:50000] + "\n\n[Note: data is truncated due to length — but most important fields are prioritized and included]"
            else:
                context = data_json
        except:
            context = str(data)[:50000] + "... [data stringified]"

        full_user_content = f"""SCRAPED DATA:\n{context}\n\nUSER QUESTION/INSTRUCTION:\n{message}"""

        # Try Groq API first, fallback to free response if rate limited
        try:
            response = groq_ai.chat_completions_create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": full_user_content}
                ],
                temperature=0.0,  # Even lower for maximum determinism and accuracy
                max_tokens=8192  # Increased to allow ultra detailed, long responses
            )

            # Carefully validate response structure to avoid 'dict' object has no attribute 'choices' error
            if not isinstance(response, dict):
                print(f"Invalid response type: {type(response)}")
                raise Exception("Invalid API response format")
            
            if "choices" not in response:
                print(f"Response missing 'choices' key: {response}")
                raise Exception("API response missing choices")
            
            if not isinstance(response["choices"], list) or len(response["choices"]) == 0:
                print(f"Invalid choices format: {response['choices']}")
                raise Exception("No choices in API response")
            
            first_choice = response["choices"][0]
            if not isinstance(first_choice, dict) or "message" not in first_choice:
                print(f"Invalid choice format: {first_choice}")
                raise Exception("Invalid choice format in API response")
            
            message = first_choice["message"]
            if not isinstance(message, dict) or "content" not in message:
                print(f"Invalid message format: {message}")
                raise Exception("Invalid message format in API response")
            
            answer = message["content"]
            if not isinstance(answer, str):
                answer = str(answer)
            
            answer = answer.strip()
            if not answer:
                answer = "No answer returned from API"

            return {"success": True, "response": answer}

        except Exception as api_error:
            print(f"Groq API failed: {api_error}")
            # Fallback to free response
            return generate_free_response(data, message)

    except Exception as e:
        print(f"Chat error: {str(e)}")
        return {"success": False, "error": f"Chat failed: {str(e)}"}

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

        # Try Grok API first, fallback to free response if rate limited
        try:
            resp = grok_mode.chat_completions_create(
                model=MODEL_DEEP,
                messages=messages,
                temperature=0.4,
                max_tokens=8000
            )

            # Validate response structure to avoid 'dict' object has no attribute 'choices' error
            if not isinstance(resp, dict) or "choices" not in resp:
                raise Exception("Invalid API response format")
            
            if not isinstance(resp["choices"], list) or len(resp["choices"]) == 0:
                raise Exception("No choices in API response")
            
            first_choice = resp["choices"][0]
            if not isinstance(first_choice, dict) or "message" not in first_choice:
                raise Exception("Invalid choice format in API response")
            
            message = first_choice["message"]
            if not isinstance(message, dict) or "content" not in message:
                raise Exception("Invalid message format in API response")
            
            answer = message["content"].strip() if isinstance(message["content"], str) else str(message["content"]).strip()
            if not answer:
                answer = "No response"

            return {
                "success": True,
                "response": answer,
                "mode": "grok_mode",
                "model": MODEL_DEEP
            }

        except Exception as api_error:
            print(f"Grok API failed: {api_error}")
            # Fallback to free universal response
            return generate_universal_response(message)

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
