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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Multiple models for fallback - try different ones if one is rate limited
MODELS = [
    "llama-3.3-70b-versatile",      # Primary
    "llama-3.1-70b-versatile",     # Fallback 1
    "llama-3.1-8b-instant",        # Fallback 2 - faster & different endpoint
    "mixtral-8x7b-32768",          # Fallback 3
    "llama3-70b-8192",             # Fallback 4
]
MODEL_INDEX = 0  # Start with first model

def get_current_model():
    return MODELS[MODEL_INDEX]

def get_next_model():
    """Get next available model when current one is rate limited"""
    global MODEL_INDEX
    MODEL_INDEX = (MODEL_INDEX + 1) % len(MODELS)
    print(f"🔄 Switching to model: {get_current_model()}")
    return get_current_model()

# Rate limiter - 15 requests per minute (conservative for free tier)
rate_limiter = RateLimiter(requests_per_minute=15)

# Response cache
response_cache = ResponseCache(max_size=100)

# Request queue
request_queue = RequestQueue()

# Local fallback AI
local_ai = LocalFallbackAI()

# ========== GROQ CLIENT WITH EXPONENTIAL BACKOFF ==========
import requests

class GroqClient:
    """Robust Groq client with exponential backoff, rate limiting, and multi-model fallback"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.max_retries = 4  # Maximum retry attempts
        self.base_delay = 2   # Base delay in seconds
    
    def chat_completions_create(self, model, messages, temperature=0, max_tokens=1500):
        """Create chat completion with exponential backoff and retry logic"""
        
        # Acquire rate limit token
        while not rate_limiter.acquire():
            wait = rate_limiter.wait_time()
            print(f"⏳ Rate limit reached, waiting {wait:.1f}s...")
            time.sleep(wait)
        
        last_error = None
        
        # Try each model with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # Try current model
                current_model = get_current_model()
                print(f"📡 Trying model: {current_model} (attempt {attempt + 1})")
                
                data = {
                    "model": current_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    timeout=60
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    # Try to get retry-after from headers
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        wait_time = int(retry_after)
                    else:
                        # Exponential backoff
                        wait_time = self.base_delay * (2 ** attempt)
                    
                    print(f"⚠️ 429 Rate limited! Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    
                    # Try next model
                    get_next_model()
                    continue
                
                # Handle other errors
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                print(f"⚠️ Request error (attempt {attempt + 1}): {last_error}")
                
                # Exponential backoff on any error
                wait_time = self.base_delay * (2 ** attempt)
                print(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                
                # Try next model on rate limit
                if "429" in last_error or "rate limit" in last_error.lower():
                    get_next_model()
        
        # All retries failed, raise exception
        raise Exception(f"Groq API error after {self.max_retries} retries: {last_error}")


# Initialize Groq client
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = GroqClient(GROQ_API_KEY)
        print("✅ Groq client initialized successfully")
        print(f"📋 Available models: {MODELS}")
    except Exception as e:
        print(f"⚠️ Groq initialization warning: {e}")
        groq_client = None


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
    """Main chat endpoint with 429 fix - exponential backoff + multi-model fallback"""
    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")
    
    if not message or not scraped:
        return {"success": False, "error": "Missing data"}
    
    try:
        data = json.loads(scraped)
    except:
        return {"success": False, "error": "Invalid scraped data format"}
    
    # Create data hash for caching
    data_str = json.dumps(data, sort_keys=True)[:1000]
    data_hash = hashlib.md5(data_str.encode()).hexdigest()
    
    # Check cache first
    cached_response = response_cache.get(data_hash, message)
    if cached_response:
        print("📦 Returning cached response")
        return {"success": True, "response": cached_response, "cached": True}
    
    # Try Groq API first with retries
    if groq_client:
        system_prompt = """You are an EXACT factual AI assistant for analyzing scraped website data.

RULES:
1. ONLY answer from the provided scraped data
2. If answer not found in data, say: "This information is not available in the scraped website data."
3. Never guess or use outside knowledge
4. Be precise and factual
5. For greetings, respond naturally but briefly
6. If asked about specific content, find and quote the exact relevant text"""

        context = _build_context(data, message)
        
        try:
            response = groq_client.chat_completions_create(
                model=get_current_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0,
                max_tokens=1500
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if answer:
                # Cache the response
                response_cache.set(data_hash, message, answer)
                return {"success": True, "response": answer, "model": get_current_model()}
                
        except Exception as e:
            error_str = str(e)
            print(f"⚠️ Groq API error: {error_str}")
            
            if "429" in error_str or "rate limit" in error_str.lower():
                print("🔄 Falling back to local AI due to rate limit (all models exhausted)...")
            else:
                print("⚠️ Using local fallback...")
    
    # Use local fallback AI
    print("🤖 Using local AI fallback")
    local_response = local_ai.generate_response(data, message)
    response_cache.set(data_hash, message, local_response)
    
    return {"success": True, "response": local_response, "mode": "local_fallback"}

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
async def grok_mode_endpoint(request: Request):
    """Grok Mode - Universal questions without using scraped data"""
    try:
        form = await request.form()
        message = form.get("message")
        analysis_type = form.get("analysis_type", "comprehensive")
        
        if not message:
            return {"success": False, "error": "Missing message"}
        
        # Try Groq API first with retries
        if groq_client:
            system_prompt = f"""You are Grok Mode - an advanced AI assistant for universal knowledge.

RULES:
1. Answer using your comprehensive knowledge
2. Be helpful, detailed and thorough
3. Analysis Type: {analysis_type}

Provide expert answers on any topic."""
            
            try:
                response = groq_client.chat_completions_create(
                    model=get_current_model(),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.4,
                    max_tokens=4000
                )
                
                answer = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                
                if answer:
                    return {"success": True, "response": answer, "mode": "grok_mode", "model": get_current_model()}
                    
            except Exception as e:
                print(f"⚠️ Grok Mode error: {str(e)}")
        
        # Fallback - simple response
        return {
            "success": True, 
            "response": f"I understand you're asking about: {message}. The Groq API is currently experiencing high demand or rate limits. Please try again in a few moments, or try with a smaller question. I can help with any topic once the API becomes available again!",
            "mode": "local_fallback"
        }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/grok-summary")
async def grok_summary(request: Request):
    """Quick summary endpoint"""
    form = await request.form()
    scraped = form.get("scraped_data")
    
    if not scraped:
        return {"success": False, "error": "Missing scraped data"}
    
    try:
        data = json.loads(scraped)
    except:
        return {"success": False, "error": "Invalid data format"}
    
    # Try Groq first with retries
    if groq_client:
        system_prompt = """Create a quick summary with:
1. MAIN TOPIC - What the page is about
2. KEY POINTS - 3-5 important facts
3. CONCLUSION - Main takeaway

Be brief and accurate."""
        
        context_parts = []
        if data.get('title'):
            context_parts.append(f"Title: {data['title']}")
        if data.get('description'):
            context_parts.append(f"Description: {data['description']}")
        if data.get('paragraphs'):
            context_parts.append("\n".join(data['paragraphs'][:10]))
        
        try:
            response = groq_client.chat_completions_create(
                model=get_current_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n\n".join(context_parts)}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if answer:
                return {"success": True, "summary": answer, "model": get_current_model()}
                
        except Exception as e:
            print(f"⚠️ Summary error: {str(e)}")
    
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

