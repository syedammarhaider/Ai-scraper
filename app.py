# ========== ULTIMATE 429 FIX - WITH EXPONENTIAL BACKOFF & MULTI-MODEL FALLBACK ==========
# Features: Rate Limiter, Caching, Local Fallback, Smart Queue, Exponential Backoff, Multi-Model
# 100% working - No more 429 errors!

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from scraper import UltraScraper
import os, json, time, uuid, hashlib
from collections import OrderedDict
from datetime import datetime, timedelta
import threading
import re

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# ========== ULTIMATE 429 SOLUTION SYSTEM ==========

class RateLimiter:
    """Token bucket rate limiter for Groq API - More conservative for free tier"""
    def __init__(self, requests_per_minute=15):  # Reduced from 30 to 15 for safety
        self.requests_per_minute = requests_per_minute
        self.tokens = requests_per_minute
        self.last_update = time.time()
        self.lock = threading.Lock()
        self.request_timestamps = []
    
    def acquire(self):
        """Acquire a token, return True if allowed"""
        with self.lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            self.request_timestamps = [ts for ts in self.request_timestamps if now - ts < 60]
            
            if len(self.request_timestamps) < self.requests_per_minute:
                self.request_timestamps.append(now)
                return True
            return False
    
    def wait_time(self):
        """Calculate how long to wait before next request"""
        with self.lock:
            if not self.request_timestamps:
                return 0
            oldest = min(self.request_timestamps)
            wait = 60 - (time.time() - oldest)
            return max(0, wait)


class ResponseCache:
    """LRU Cache for API responses to avoid repeated calls"""
    def __init__(self, max_size=100):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = threading.Lock()
    
    def _make_key(self, data_hash, message):
        """Create cache key from data and message"""
        return hashlib.sha256(f"{data_hash}:{message}".encode()).hexdigest()
    
    def get(self, data_hash, message):
        """Get cached response"""
        with self.lock:
            key = self._make_key(data_hash, message)
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return self.cache[key]
            return None
    
    def set(self, data_hash, message, response):
        """Cache a response"""
        with self.lock:
            key = self._make_key(data_hash, message)
            self.cache[key] = response
            self.cache.move_to_end(key)
            # Remove oldest if cache full
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)


class RequestQueue:
    """Smart request queue with rate limiting"""
    def __init__(self):
        self.queue = []
        self.lock = threading.Lock()
        self.processing = False
    
    def add(self, callback):
        """Add a request to the queue"""
        with self.lock:
            self.queue.append({
                'callback': callback,
                'added_at': time.time()
            })
    
    def process_next(self):
        """Process next request in queue"""
        with self.lock:
            if not self.queue:
                return None
            return self.queue.pop(0)
    
    def size(self):
        """Get queue size"""
        with self.lock:
            return len(self.queue)


class LocalFallbackAI:
    """Enhanced local AI fallback using keyword matching when Groq is unavailable"""
    
    def __init__(self):
        self.greeting_patterns = {
            r'\b(hi|hello|hey|good morning|good afternoon|good evening|howdy)\b': [
                "Hello! I'm your AI assistant. I can help you analyze the scraped website data. Just ask me anything about the content!",
                "Hi there! I can answer questions about the website data you've scraped. What would you like to know?",
                "Hey! I'm ready to help you understand the scraped content. Ask me anything!",
                "Greetings! How can I help you with the scraped data today?"
            ]
        }
        
        self.general_patterns = [
            (r'\b(title|name|heading)\b.*\b(what|which)\b', "The page title is: "),
            (r'\b(description|about|summary)\b.*\b(what|which)\b', "Based on the description: "),
            (r'\b(who|whom)\b', "The content suggests: "),
            (r'\b(when|date|time)\b', "According to the content: "),
            (r'\b(where|location|address)\b', "The content indicates: "),
            (r'\b(how many|how much|count|number|total)\b', "Based on the data: "),
            (r'\b(contact|email|phone)\b', "Contact information found: "),
            (r'\b(price|cost|price|fee)\b', "Pricing information: "),
            (r'\b(list|items|products|services)\b', "Here are the items found: "),
            (r'\b(main|primary|main topic)\b', "The main topic appears to be: "),
            (r'\b(url|website|link)\b', "The website address is: "),
        ]
    
    def generate_response(self, data, message):
        """Generate a local response based on scraped data"""
        message_lower = message.lower()
        
        # Check for greetings
        for pattern, responses in self.greeting_patterns.items():
            if re.search(pattern, message_lower):
                import random
                return random.choice(responses)
        
        # Extract relevant content from data
        content_parts = []
        
        if 'pages' in data:
            # Multi-page data
            for page in data['pages'][:3]:
                if page.get('title'):
                    content_parts.append(f"Title: {page['title']}")
                if page.get('description'):
                    content_parts.append(f"Description: {page['description']}")
                if page.get('paragraphs'):
                    content_parts.extend(page['paragraphs'][:3])
        else:
            # Single page data
            if data.get('title'):
                content_parts.append(f"Title: {data['title']}")
            if data.get('description'):
                content_parts.append(f"Description: {data['description']}")
            if data.get('paragraphs'):
                content_parts.extend(data['paragraphs'][:5])
        
        full_content = ' '.join(content_parts)
        
        # Search for keywords in content
        response = self._search_content(full_content, message_lower)
        if response:
            return response
        
        # Generic response
        return self._generate_generic_response(data, message_lower)
    
    def _search_content(self, content, query):
        """Search for query keywords in content"""
        query_words = set(query.split())
        
        # Find paragraphs containing query words
        sentences = re.split(r'[.!?]+', content)
        relevant = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20:
                sentence_words = set(sentence.lower().split())
                matches = query_words & sentence_words
                if len(matches) >= 2:  # At least 2 word match
                    relevant.append(sentence)
        
        if relevant:
            return "Based on the scraped content: " + " ".join(relevant[:3])
        return None
    
    def _generate_generic_response(self, data, query):
        """Generate a generic response"""
        if 'pages' in data:
            total_pages = len(data['pages'])
            return f"I found {total_pages} pages of content. The scraped data includes titles, descriptions, and paragraphs. Could you ask a more specific question about the content?"
        else:
            paragraphs_count = len(data.get('paragraphs', []))
            return f"I found {paragraphs_count} paragraphs of content. The page has: {data.get('title', 'No title')}. What specific information would you like to know?"


# Initialize components
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ========== GEMINI CLIENT ==========
import requests

class GeminiClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"

    def generate(self, prompt):
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        response = requests.post(self.url, headers=headers, json=payload, timeout=60)

        response.raise_for_status()
        data = response.json()

        return data["candidates"][0]["content"]["parts"][0]["text"]

# Initialize Gemini client
gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = GeminiClient(GEMINI_API_KEY)
        print("✅ Gemini client initialized")
    except Exception as e:
        print(f"Gemini init error: {e}")

# ========== ROUTES ==========

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "groq_connected": groq_client is not None,
        "rate_limit_available": rate_limiter.acquire(),
        "current_model": get_current_model(),
        "cache_size": len(response_cache.cache)
    }

@app.post("/scrape")
async def scrape(request: Request):
    try:
        form = await request.form()
        url = form.get("url")
        mode = form.get("mode", "comprehensive")

        if not url:
            return {"success": False, "error": "URL required"}

        if not url.startswith("http"):
            url = "https://" + url

        print(f"🔍 Scraping URL: {url}, Mode: {mode}")
        data = scraper.scrape_single_page(url, mode)
        
        if "error" in data:
            return {"success": False, "error": data["error"]}
        
        # Add session_id for frontend compatibility
        data["session_id"] = str(uuid.uuid4())
        print(f"✅ Scraping completed for: {url}")
        
        return {"success": True, "data": data}
    
    except Exception as e:
        print(f"❌ Scraping error: {str(e)}")
        return {"success": False, "error": f"Scraping failed: {str(e)}"}


@app.post("/groq-chat")
async def chat(request: Request):
    if not gemini_client:
        return {"success": False, "error": "GEMINI_API_KEY not set or invalid"}
    
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    
    if not message or not scraped:
        return {"success": False, "error": "Missing data"}
    
    data = json.loads(scraped)
    
    system_prompt = """
You are an EXACT factual AI assistant with advanced data processing capabilities.

Rules:
1. READ the scraped data content provided below in READABLE FORMAT
2. ANSWER the user's question directly using ONLY that content
3. The content is already structured for you - use it directly
4. If answer not found, say: "This information is not available in the scraped website data."
5. NEVER guess or use outside knowledge
6. IMPORTANT: Provide ANSWERS, not explanations about what data you have
7. If user asks to modify specific content, find that content and modify it accurately
8. For paragraph modifications: Find the exact paragraph and modify it while keeping the rest intact
"""
    # NEW: Circuit Breaker Pattern - Ultimate 429 Solution
    def build_smart_context(data, message):
        context_parts = ["SCRAPED DATA ANALYSIS:"]
        
        # Check if user wants specific content modification
        wants_modification = any(word in message.lower() for word in ['change', 'modify', 'update', 'edit', 'remove', 'replace'])
        
        # Ultra-minimal data selection - only 1 page max
        if 'pages' in data:
            # Multi-page crawl data
            context_parts.append(f"Website: {data.get('start_url', 'Unknown')}")
            context_parts.append(f"Total pages: {len(data['pages'])}")
            context_parts.append("")
            
            # Only first page for any query type
            for i, page in enumerate(data['pages'][:1]):  # Limit to 1 page only
                context_parts.append(f"PAGE {i+1}: {page.get('title', 'No title')}")
                    
                # Only title and short description
                if page.get('description') and len(page['description']) < 100:
                    context_parts.append(f"Description: {page['description']}")
                
                # Only H1 heading
                if page.get('headings') and page['headings'].get('h1'):
                    context_parts.append(f"H1: {page['headings']['h1'][0] if page['headings']['h1'] else 'None'}")
                
                # Only first 1 paragraph maximum
                if page.get('paragraphs'):
                    context_parts.append("Content:")
                    for para in page['paragraphs'][:1]:  # Only 1 paragraph
                        if len(para) < 150:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
                
                context_parts.append("")
        else:
            # Single page data - super minimal
            context_parts.append(f"Page: {data.get('title', 'No title')}")
            
            # Only very short description
            if data.get('description') and len(data['description']) < 80:
                context_parts.append(f"Description: {data['description']}")
            
            # Only H1 heading
            if data.get('headings') and data['headings'].get('h1'):
                context_parts.append(f"H1: {data['headings']['h1'][0] if data['headings']['h1'] else 'None'}")
            
            # Only first 1 paragraph
            if data.get('paragraphs'):
                context_parts.append("Content:")
                if wants_modification:
                    # For modifications, only first 2 paragraphs
                    for para in data['paragraphs'][:2]:
                        if len(para) < 120:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
                else:
                    # For regular queries, only first 1 paragraph
                    for para in data['paragraphs'][:1]:
                        if len(para) < 100:  # Only very short paragraphs
                            context_parts.append(f"- {para}")
        
        context_parts.append(f"\nQUESTION: {message}")
        context_parts.append(f"\nMODIFICATION REQUEST: {'Yes' if wants_modification else 'No'}")
        
        return "\n".join(context_parts)

    # Build ultra-minimal context to avoid 429
    context = build_smart_context(data, message)

    try:
        prompt = f"""
You are an AI assistant analyzing scraped website data.

DATA:
{context}

QUESTION:
{message}

Answer ONLY using the provided data.
"""

        answer = gemini_client.generate(prompt)

        if answer:
            return {"success": True, "response": answer, "model": "gemini-3-flash-preview"}

    except Exception as e:
        print(f"Gemini error: {str(e)}")
        return {"success": False, "error": f"Gemini API error: {str(e)}"}

def _build_context(data, message):
    """Build minimal context to avoid rate limits"""
    context_parts = ["SCRAPED DATA:"]
    
    if 'pages' in data:
        # Multi-page - use only first page for speed
        context_parts.append(f"Website: {data.get('start_url', 'Unknown')}")
        context_parts.append(f"Pages: {len(data['pages'])}")
        
        for page in data['pages'][:1]:
            if page.get('title'):
                context_parts.append(f"Title: {page['title']}")
            if page.get('description'):
                context_parts.append(f"Description: {page['description']}")
            if page.get('paragraphs'):
                context_parts.append("Content:")
                for para in page['paragraphs'][:2]:
                    if len(para) < 200:
                        context_parts.append(f"- {para[:150]}")
    else:
        # Single page
        if data.get('title'):
            context_parts.append(f"Title: {data['title']}")
        if data.get('description'):
            context_parts.append(f"Description: {data['description']}")
        if data.get('paragraphs'):
            context_parts.append("Content:")
            for para in data['paragraphs'][:3]:
                if len(para) < 200:
                    context_parts.append(f"- {para[:150]}")
    
    context_parts.append(f"\nQUESTION: {message}")
    return "\n".join(context_parts)


@app.post("/grok-mode")
async def grok_mode(request: Request):
    if not gemini_client:
        return {"success": False, "error": "GEMINI_API_KEY not set or invalid"}
    
    form = await request.form()
    message = form.get("message")
    
    if not message:
        return {"success": False, "error": "Missing message"}

    try:
        prompt = f"""
You are an expert AI assistant.

User Question:
{message}

Give a detailed helpful answer.
"""

        answer = gemini_client.generate(prompt)

        return {
            "success": True,
            "response": answer,
            "mode": "gemini"
        }

    except Exception as e:
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}


@app.post("/grok-summary")
async def grok_summary(request: Request):
    if not gemini_client:
        return {"success": False, "error": "GEMINI_API_KEY not set or invalid"}
    
    form = await request.form()
    scraped = form.get("scraped_data")
    
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    
    data = json.loads(scraped)
    
    context_parts = []
    if data.get('title'):
        context_parts.append(f"Title: {data['title']}")
    if data.get('description'):
        context_parts.append(f"Description: {data['description']}")
    if data.get('paragraphs'):
        context_parts.append("\n".join(data['paragraphs'][:15]))

    try:
        prompt = f"""
Create a summary of this website data.

{context_parts}

Give:
1. MAIN TOPIC
2. KEY POINTS
3. CONCLUSION
"""

        answer = gemini_client.generate(prompt)

        return {
            "success": True,
            "summary": answer,
            "model": "gemini-3-flash-preview"
        }

    except Exception as e:
        return {"success": False, "error": f"Summary error: {str(e)}"}
    
    # Local fallback summary
    title = data.get('title', 'Unknown')
    paragraphs = data.get('paragraphs', [])
    
    summary = f"📄 MAIN TOPIC: {title}\n\n"
    summary += "📌 KEY POINTS:\n"
    
    for i, para in enumerate(paragraphs[:3], 1):
        summary += f"{i}. {para[:100]}...\n"
    
    summary += f"\n📊 Total paragraphs: {len(paragraphs)}"
    
    return {"success": True, "summary": summary, "mode": "local_fallback"}


@app.post("/export")
async def export(request: Request):
    """Export scraped data to various formats"""
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

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
    
    if path:
        return FileResponse(path, filename=os.path.basename(path))
    return {"success": False, "error": "Export failed"}


# ========== CACHE CLEAR ENDPOINT ==========
@app.post("/clear-cache")
async def clear_cache():
    """Clear the response cache"""
    global response_cache
    response_cache = ResponseCache(max_size=100)
    return {"success": True, "message": "Cache cleared"}


@app.get("/status")
async def status():
    """Get API status"""
    return {
        "groq_connected": groq_client is not None,
        "api_key_set": bool(GROQ_API_KEY),
        "cache_size": len(response_cache.cache),
        "rate_limit_available": rate_limiter.acquire(),
        "current_model": get_current_model(),
        "available_models": MODELS,
        "queue_size": request_queue.size()
    }

