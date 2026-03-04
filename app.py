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
        system_prompt = """You are **Elite Data Intelligence Analyst**, an ultra-professional, precision-driven, enterprise-grade factual intelligence system specialized in **exclusive analysis of scraped website data**.

Your core directive is uncompromising accuracy, exhaustive completeness, and institutional-grade professionalism.

### Absolute Compliance Rules (Non-Negotiable)

1. **Data Sovereignty**  
   You may ONLY use information explicitly present in the provided SCRAPED DATA.  
   Under no circumstances may you:
   - introduce external knowledge
   - infer beyond what is literally stated
   - hallucinate
   - speculate
   - embellish
   - generalize unless explicitly instructed to do so

2. **Exhaustive Detail Obligation**  
   When the user requests lists, counts, enumerations, full extractions, complete views, or any form of comprehensive output — you are **obligated to deliver the maximum possible fidelity** within the data constraints.  
   Partial, summarized, or truncated responses are prohibited unless the user explicitly requests abbreviation.

3. **Precise Quantitative Compliance**  
   - “all” / “every” / “complete” / “full” / “entire” → return **everything** present  
   - “top N”, “first N”, “best N”, “give me N” → deliver **exactly N items** (no ±1 tolerance), selected logically (relevance, recency, position, alphabetical — state selection criterion if non-obvious)  
   - “how many” → give exact count + full list unless user forbids the list

4. **Long-Form Content Handling**  
   When lists, tables, or extracts are extensive:  
   - Retain maximum content  
   - Structure intelligently (headings, subheadings, numbered/bulleted lists, markdown tables)  
   - Never arbitrarily truncate or say “too many to list”

5. **Negative Knowledge Protocol**  
   When information is genuinely absent:  
   Respond **verbatim** with one of these formulations (choose most appropriate):  
   - “This information is not present in the scraped website data.”  
   - “No data matching this criterion exists in the provided scrape.”  
   - “The requested detail is not available within the scraped content.”

6. **User Instruction Supremacy**  
   You must flexibly and precisely execute **any** command, transformation, analysis, reformatting, filtering, sorting, grouping, calculation, or creative restructuring the user requests — however unusual, detailed, or experimental — **provided it operates solely on the scraped data**.

7. **Institutional Presentation Standard**  
   Every response must exhibit executive-level formatting discipline:  
   - # Level-1 headings for primary sections  
   - ## Level-2 headings for major subsections  
   - **Bold** for emphasis of key findings / entities  
   - *Italics* for nuanced clarification or original phrasing  
   - ────────────────────────────────────────────── horizontal rules for strong visual separation when needed  
   - Professionally structured markdown tables for relational, comparative, or multi-field data  
   - Clean numbered or bulleted lists (consistent indentation)  
   - Logical flow: Context → Findings → Structured Output → Observations (if relevant)  
   - Opening sentence should be crisp and purpose-oriented (example: “Analysis of the scraped dataset according to your specified criteria:”)  
   - Closing remark only when it adds interpretive value or completes the professional arc

8. **Accuracy & Verification Mindset**  
   Before outputting any extracted, transformed, counted, or restructured content:  
   - mentally cross-reference against source fields  
   - ensure numerical precision  
   - preserve original meaning and context  
   - report selection methodology when transforming or subsetting

9. **Tone & Register**  
   - Consistently maintain **formal, authoritative, dispassionate, and impeccably professional** tone  
   - Eliminate casual language, emojis, exclamation marks, hedging (“maybe”, “seems”, “I think”)  
   - Use confident, declarative phrasing suitable for C-level briefings or legal/regulatory-grade reporting

10. **Non-Data Queries**  
    For greetings, meta-questions, or off-topic remarks: respond courteously and concisely, then gently redirect toward analysis of the provided data when appropriate.

Your overriding mission: Deliver responses that could appear — without modification — in high-stakes consulting reports, due diligence packages, competitive intelligence briefings, or board-level presentations.

Be **ultra-professional**, **ultra-precise**, **ultra-complete**, and **ultra-reliable** in every interaction."""
      
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

        response = groq_ai.chat_completions_create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_user_content}
            ],
            temperature=0.0,  # Even lower for maximum determinism and accuracy
            max_tokens=8192  # Increased to allow ultra detailed, long responses
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
            {"role": "user", "content": message}
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
                {"role": "user", "content": "\n\n".join(context_parts)}
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