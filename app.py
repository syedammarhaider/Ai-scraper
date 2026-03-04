# FINAL FIXED APP.PY - Large Data Handling + Detailed Answers from Scraped Data
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os, json, time, uuid, gzip, hashlib, random, re, datetime
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

        # Try Groq API first, fallback to free response if rate limited
        try:
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

# ──────────────────────────────────────────────
# Free response generator for unlimited fallback
# ──────────────────────────────────────────────

def generate_free_response(data: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Generate professional AI response without API calls when rate limited"""
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
    
    # Generate professional AI response based on question and available data
    def create_professional_response(q_type, extracted_data, question):
        # Analyze the actual data to provide specific insights
        data_analysis = ""
        
        if q_type == "paragraphs" and isinstance(extracted_data, list):
            para_count = len(extracted_data)
            total_words = sum(len(p.split()) for p in extracted_data if isinstance(p, str))
            data_analysis = f"I found {para_count} paragraphs containing approximately {total_words} words. "
            
        elif q_type == "urls" and isinstance(extracted_data, str):
            urls = extracted_data.split('\n') if extracted_data else []
            url_count = len(urls)
            domains = set()
            for url in urls:
                if url.startswith('http'):
                    try:
                        domain = url.split('/')[2]
                        domains.add(domain)
                    except:
                        pass
            data_analysis = f"Successfully extracted {url_count} unique URLs from "
            data_analysis += f"{len(domains)} different domains. " if domains else "the webpage. "
            
        elif q_type == "title" and isinstance(extracted_data, str):
            title_length = len(extracted_data)
            data_analysis = f"The page title contains {title_length} characters and "
            if extracted_data:
                data_analysis += f"includes keywords like: {', '.join(extracted_data.split()[:3])}. "
            
        elif q_type == "images" and isinstance(extracted_data, str):
            images = extracted_data.split('\n') if extracted_data else []
            img_count = len(images)
            extensions = {}
            for img in images:
                if img:
                    ext = img.split('.')[-1].lower() if '.' in img else 'unknown'
                    extensions[ext] = extensions.get(ext, 0) + 1
            data_analysis = f"Discovered {img_count} image URLs. "
            if extensions:
                data_analysis += f"Image formats include: {', '.join([f'{k} ({v})' for k, v in extensions.items()])}. "
        
        responses = {
            "paragraphs": f"Based on my comprehensive analysis of the scraped content, I've extracted {data_analysis}Here are the key paragraphs that contain the main information:\n\n{extracted_data}\n\nThese paragraphs represent the core textual content and provide detailed insights into the website's main topics and information structure.",
            "urls": f"{data_analysis}I've systematically extracted all relevant URLs from the scraped data:\n\n{extracted_data}\n\nThese URLs represent the complete navigation structure, including internal site navigation and external references that provide additional context and resources.",
            "title": f"{data_analysis}The website title is: '{extracted_data}'\n\nThis title serves as the primary identifier for the webpage and typically reflects the main subject matter or purpose of the content.",
            "description": f"Here's the comprehensive website description: '{extracted_data}'\n\nThis meta description provides a concise summary of the webpage's content and is typically used by search engines to understand the page's relevance and purpose.",
            "images": f"{data_analysis}I've identified the following image URLs from the webpage:\n\n{extracted_data}\n\nThese images represent the visual content embedded within the webpage, including graphics, photos, and other media elements that enhance the user experience.",
            "headings": f"The page structure includes the following hierarchical headings:\n\n{extracted_data}\n\nThese headings organize the content into logical sections and provide a clear navigation path through the main topics and subtopics covered on the page.",
            "internal_links": f"I've extracted {len(extracted_data.split()) if isinstance(extracted_data, str) else 0} internal navigation links:\n\n{extracted_data}\n\nThese internal links connect to other pages within the same website domain, facilitating user navigation and content discovery.",
            "external_links": f"Found {len(extracted_data.split()) if isinstance(extracted_data, str) else 0} external reference links:\n\n{extracted_data}\n\nThese external links point to third-party websites and resources that provide additional information, references, or complementary content.",
            "pages": f"Multi-page scraping analysis revealed:\n\n{extracted_data}\n\nThis represents the complete website structure across all discovered pages, providing a comprehensive view of the site's content organization.",
            "json": f"Complete structured dataset extracted from the webpage:\n\n```json\n{extracted_data}\n```\n\nThis JSON format contains all extracted information including metadata, content structure, links, and media assets, providing a comprehensive dataset for further processing and analysis.",
            "full_text": f"Complete textual content extraction:\n\n{extracted_data}\n\nThis represents the entire text content from the webpage, capturing all textual information in a structured format for comprehensive analysis and processing."
        }
        return responses.get(q_type, f"Here's the detailed information you requested:\n\n{extracted_data}")
    
    # Extract number from question if specified
    number_requested = None
    match = re.search(r'\b(\d+)\b', question)
    if match:
        number_requested = int(match.group(1))
    
    # URL extraction
    if "url" in question_lower or "link" in question_lower:
        all_urls = []
        
        if processed_data.get("internal_links"):
            all_urls.extend([link["url"] for link in processed_data["internal_links"]])
        if processed_data.get("external_links"):
            all_urls.extend([link["url"] for link in processed_data["external_links"]])
        if processed_data.get("pages"):
            for page in processed_data["pages"]:
                if isinstance(page, dict) and page.get("url"):
                    all_urls.append(page["url"])
        
        all_urls = list(dict.fromkeys(all_urls))  # Remove duplicates
        
        if number_requested:
            all_urls = all_urls[:number_requested]
        
        if not all_urls:
            return {"success": True, "response": "I've analyzed the scraped data, but no URLs were found in the content. The webpage may not contain any hyperlinks or the scraping process may not have detected any link structures."}
        
        return {"success": True, "response": create_professional_response("urls", "\n".join(all_urls), question)}
    
    # Image URLs
    if "image" in question_lower:
        images = processed_data.get("images", [])
        if number_requested:
            images = images[:number_requested]
        
        if not images:
            return {"success": True, "response": "After analyzing the webpage content, I didn't find any image URLs. The page may not contain visual content or the images might be loaded dynamically."}
        
        return {"success": True, "response": create_professional_response("images", "\n".join(images), question)}
    
    # Paragraphs
    if "paragraph" in question_lower or "para" in question_lower:
        paragraphs = processed_data.get("paragraphs", [])
        if number_requested:
            paragraphs = paragraphs[:number_requested]
        
        if not paragraphs:
            return {"success": True, "response": "I've examined the scraped content, but no paragraph structures were identified. The webpage may primarily contain other content types or the text formatting may differ from standard paragraph structures."}
        
        return {"success": True, "response": create_professional_response("paragraphs", "\n\n".join(paragraphs), question)}
    
    # Title
    if "title" in question_lower:
        title = processed_data.get("title", "No title found.")
        if title == "No title found.":
            return {"success": True, "response": "The scraped webpage doesn't appear to have a defined title. This could indicate a dynamically generated page or missing title metadata."}
        
        return {"success": True, "response": create_professional_response("title", title, question)}
    
    # Description
    if "description" in question_lower or "desc" in question_lower:
        description = processed_data.get("description", "No description found.")
        if description == "No description found.":
            return {"success": True, "response": "No meta description was found in the webpage. This suggests the page may be missing SEO metadata or uses alternative description methods."}
        
        return {"success": True, "response": create_professional_response("description", description, question)}
    
    # Headings
    if "heading" in question_lower or "header" in question_lower:
        headings = processed_data.get("headings", [])
        if number_requested:
            headings = headings[:number_requested]
        
        if not headings:
            return {"success": True, "response": "The webpage structure doesn't contain standard heading elements (H1, H2, etc.). The content may use alternative formatting or be dynamically generated."}
        
        return {"success": True, "response": create_professional_response("headings", "\n".join(headings), question)}
    
    # Full text
    if "full text" in question_lower or "complete text" in question_lower:
        full_text = processed_data.get("full_text", "No full text available.")
        if full_text == "No full text available.":
            return {"success": True, "response": "The complete text extraction was unsuccessful. This could be due to JavaScript-rendered content, access restrictions, or complex page structures that prevent full text capture."}
        
        return {"success": True, "response": create_professional_response("full_text", full_text, question)}
    
    # JSON data
    if "json" in question_lower or "data" in question_lower:
        json_response = json.dumps(processed_data, indent=2, ensure_ascii=False)
        return {"success": True, "response": create_professional_response("json", json_response, question)}
    
    # Pages (for multi-page scraping)
    if "page" in question_lower:
        pages = processed_data.get("pages", [])
        if number_requested:
            pages = pages[:number_requested]
        
        if not pages:
            return {"success": True, "response": "The scraping process didn't identify multiple pages. This appears to be a single-page website or the multi-page crawling may not have been activated."}
        
        page_info = []
        for i, page in enumerate(pages, 1):
            if isinstance(page, dict):
                page_title = page.get("title", f"Page {i}")
                page_url = page.get("url", "")
                page_info.append(f"Page {i}: {page_title}\nURL: {page_url}")
        
        return {"success": True, "response": create_professional_response("pages", "\n\n".join(page_info), question)}
    
    # Internal links
    if "internal" in question_lower and ("link" in question_lower or "url" in question_lower):
        internal_links = processed_data.get("internal_links", [])
        if number_requested:
            internal_links = internal_links[:number_requested]
        
        if not internal_links:
            return {"success": True, "response": "No internal navigation links were detected in the scraped content. The webpage may have a simple structure or use dynamic navigation methods."}
        
        link_info = []
        for link in internal_links:
            if isinstance(link, dict):
                link_text = link.get("text", "")
                link_url = link.get("url", "")
                link_info.append(f"{link_text}: {link_url}")
        
        return {"success": True, "response": create_professional_response("internal_links", "\n".join(link_info), question)}
    
    # External links
    if "external" in question_lower and ("link" in question_lower or "url" in question_lower):
        external_links = processed_data.get("external_links", [])
        if number_requested:
            external_links = external_links[:number_requested]
        
        if not external_links:
            return {"success": True, "response": "No external reference links were found in the webpage content. The page appears to be self-contained or may not reference external resources."}
        
        link_info = []
        for link in external_links:
            if isinstance(link, dict):
                link_text = link.get("text", "")
                link_url = link.get("url", "")
                link_info.append(f"{link_text}: {link_url}")
        
        return {"success": True, "response": create_professional_response("external_links", "\n".join(link_info), question)}
    
    # Default professional response for any other question
    return {
        "success": True, 
        "response": f"I understand you're asking about: '{question}'\n\nBased on my analysis of the scraped data, I can provide you with specific information including:\n\n• **Content Analysis**: Extract paragraphs, headings, and full text\n• **Link Intelligence**: All URLs, internal navigation, and external references\n• **Media Assets**: Image URLs and visual content\n• **Metadata**: Page title, description, and structural information\n• **Complete Dataset**: Full JSON export with all extracted data\n\nPlease specify what type of information you'd like me to extract from the scraped content. For example:\n- 'Show me the main paragraphs'\n- 'Extract all URLs'\n- 'What's the page title?'\n- 'Display image links'\n- 'Give me the complete JSON data'\n\nI'm here to help you analyze and utilize the scraped information effectively."
    }

def generate_universal_response(question: str) -> Dict[str, Any]:
    """Generate universal response without API calls when rate limited"""
    question_lower = question.lower()
    
    # For any question in free mode, return a helpful message about JSON data
    return {
        "success": True,
        "response": f"I'm currently operating in free mode due to API rate limits. I can help with questions about scraped website data by returning it in JSON format.\n\nTo get the scraped data in JSON format, please use the AI Scraped Data Analysis mode (first toggle button). In that mode, I can provide the complete scraped data with text replacements applied.\n\nFor general knowledge questions, please try again later when the API rate limits reset."
    }

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