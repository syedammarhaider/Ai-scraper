# ============================================================
# FINAL PRODUCTION APP.PY
# Ultra-Professional Scraped Data AI Analysis Engine
# ============================================================

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from typing import Dict, Any
import os
import json
import time
import uuid
import gzip
import logging
import random
import re
import requests

from scraper import UltraScraper

# ============================================================
# INITIALIZATION
# ============================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()
app.mount("/static", StaticFiles(directory="static"), name="static")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

MAX_RESPONSE_SIZE = 50 * 1024 * 1024
MAX_PAGES_LARGE = 100

# ============================================================
# SAFE DATA HANDLING
# ============================================================

def compress_data(data: str) -> str:
    return gzip.compress(data.encode("utf-8")).hex()

def decompress_data_safe(hex_data: str) -> str:
    try:
        raw = bytes.fromhex(hex_data)
        return gzip.decompress(raw).decode("utf-8")
    except Exception:
        return hex_data

def safe_json_loads(data: Any) -> Any:
    if isinstance(data, dict):
        return data
    if not isinstance(data, str):
        return {}
    try:
        return json.loads(data)
    except Exception:
        return {}

# ============================================================
# GROQ DIRECT CLIENT (Rate-limit Safe)
# ============================================================

class GroqDirectClient:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat(self, model: str, messages, temperature=0, max_tokens=4096):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        retries = 3
        base_delay = 1

        for attempt in range(retries):
            try:
                response = requests.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 429:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logging.warning(f"Rate limit hit. Retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                result = response.json()

                if "choices" not in result:
                    raise Exception("Invalid API response format")

                return result["choices"][0]["message"]["content"].strip()

            except Exception as e:
                logging.error(f"Groq API error: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(base_delay)

        raise Exception("Groq request failed after retries")

groq_ai = GroqDirectClient(GROQ_API_KEY) if GROQ_API_KEY else None

# ============================================================
# OPTIMIZE DATA SIZE
# ============================================================

def optimize_data_size(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data_str = json.dumps(data, ensure_ascii=False)
        if len(data_str) > MAX_RESPONSE_SIZE:
            return {
                "compressed_data": compress_data(data_str),
                "is_compressed": True
            }
        return data
    except Exception:
        return data

# ============================================================
# ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "healthy"}

# ============================================================
# SCRAPE
# ============================================================

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

        logging.info(f"Scraping {url}")

        if mode == "comprehensive":
            data = scraper.crawl_website(url, mode, max_pages=max_pages)
        else:
            data = scraper.scrape_single_page(url, mode)

        if "error" in data:
            return {"success": False, "error": data["error"]}

        optimized = optimize_data_size(data)
        optimized["session_id"] = str(uuid.uuid4())
        optimized["scrape_id"] = str(uuid.uuid4())

        return {"success": True, "data": optimized}

    except Exception as e:
        logging.error(f"Scrape error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================
# ULTRA PROFESSIONAL SCRAPED DATA AI
# ============================================================

def generate_professional_response(data: Dict[str, Any], question: str) -> Dict[str, Any]:
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

@app.post("/groq-chat")
async def groq_chat(request: Request):
    try:
        form = await request.form()
        user_message = form.get("message")
        scraped_raw = form.get("scraped_data")

        if not user_message or not scraped_raw:
            return {"success": False, "error": "Missing message or scraped_data"}

        scraped_data = safe_json_loads(scraped_raw)

        if scraped_data.get("is_compressed"):
            decompressed = decompress_data_safe(scraped_data["compressed_data"])
            scraped_data = safe_json_loads(decompressed)

        context = json.dumps(scraped_data, ensure_ascii=False, indent=2)

        if len(context) > 30000:
            context = context[:30000] + "\n[DATA TRUNCATED FOR TOKEN LIMIT]"

        system_prompt = """
You are an Elite Institutional Data Intelligence System.

STRICT RULES:
1. You may ONLY use information present in the provided SCRAPED DATA.
2. Execute ANY transformation, filtering, sorting, restructuring, counting,
   comparison, extraction, grouping, or formatting command exactly as instructed.
3. If user asks for ALL data → return ALL.
4. If user specifies number N → return EXACTLY N.
5. Never guess. Never hallucinate.
6. If information does not exist, say:
   "This information is not present in the scraped website data."
7. Formatting must be executive-grade::
   - Use # headings
   - Structured lists
   - Tables when appropriate
   - Professional tone
   - No casual language
8. Be exhaustive and precise.
"""

        full_prompt = f"""
SCRAPED DATA:
{context}

USER INSTRUCTION:
{user_message}
"""

        if not groq_ai:
            # Fallback to professional response generator
            return generate_professional_response(scraped_data, user_message)

        try:
            answer = groq_ai.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0,
                max_tokens=4096
            )

            return {
                "success": True,
                "response": answer
            }

        except Exception as api_error:
            logging.error(f"Groq API failed: {api_error}")
            # Fallback to professional response generator
            return generate_professional_response(scraped_data, user_message)

    except Exception as e:
        logging.error(f"AI error: {e}")
        return {
            "success": False,
            "error": "AI analysis failed."
        }

# ============================================================
# EXPORT
# ============================================================

@app.post("/export")
async def export(request: Request):
    try:
        body = await request.json()
        fmt = body.get("format")
        data = body.get("data")

        if not fmt or not data:
            return {"success": False, "error": "Missing format or data"}

        if isinstance(data, dict) and data.get("is_compressed"):
            decompressed = decompress_data_safe(data["compressed_data"])
            data = safe_json_loads(decompressed)

        filename = f"scraped_data_{int(time.time())}"

        handlers = {
            "json": scraper.save_as_json,
            "csv": scraper.save_as_csv,
            "excel": scraper.save_as_excel,
            "txt": scraper.save_as_text,
            "pdf": scraper.save_as_pdf
        }

        if fmt not in handlers:
            return {"success": False, "error": "Unsupported format"}

        path = handlers[fmt](data, filename)
        return FileResponse(path, filename=os.path.basename(path))

    except Exception as e:
        logging.error(f"Export error: {e}")
        return {"success": False, "error": str(e)}

# ============================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )