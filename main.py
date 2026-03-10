import asyncio
import sys
import os
from typing import Any, Optional
from dotenv import load_dotenv

# ------------------- Windows Event Loop Fix ------------------- #
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ------------------- Env ------------------- #
load_dotenv()
PORT = int(os.environ.get("PORT", 8000))

# ------------------- FastAPI Core ------------------- #
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ------------------- Rate Limiting ------------------- #
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ------------------- Gemini Client ------------------- #
import google.generativeai as genai

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("You must set the GEMINI_API_KEY environment variable.")

# Create client
client = genai.GenerativeModel(model_name="gemini-3-flash-preview")

async def call_gemini(prompt: str) -> str:
    """Call Gemini API with exact prompts for accurate responses"""
    loop = asyncio.get_event_loop()

    def sync_call():
        response = client.generate_content(prompt)
        return response.text

    return await loop.run_in_executor(None, sync_call)

# ------------------- App Init ------------------- #
limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://13.60.154.214/", "http://3.95.32.144/"],  # Live server IPs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- Schemas ------------------- #
class ScrapeRequest(BaseModel):
    url: str

class FormatRequest(BaseModel):
    data: Any
    format_type: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    scraped_data: Optional[str] = None

# ------------------- Scraper Module ------------------- #
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

async def scrape_single_page(url: str) -> dict:
    """Scrape a single page with exact data extraction"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception as e:
            return {"url": url, "error": f"Failed to fetch: {str(e)}"}

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove unwanted tags
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Extract exact data
    data = {
        "url": url,
        "title": "",
        "meta_description": "",
        "headings": {"h1": [], "h2": [], "h3": [], "h4": [], "h5": [], "h6": []},
        "paragraphs": [],
        "links": [],
        "lists": [],
        "images": [],
        "tables": []
    }

    # Title
    if soup.title:
        data["title"] = soup.title.get_text(strip=True)

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        data["meta_description"] = meta["content"]

    # Headings by level
    for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                data["headings"][level].append(text)

    # Paragraphs (clean and complete)
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 10:  # Only meaningful paragraphs
            data["paragraphs"].append(text)

    # Links
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and text:
            data["links"].append({
                "url": urljoin(url, href),
                "text": text
            })

    # Lists
    for ul in soup.find_all(["ul", "ol"]):
        items = []
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                items.append(text)
        if items:
            data["lists"].append(items)

    # Images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if src:
            data["images"].append({
                "url": urljoin(url, src),
                "alt": alt
            })

    # Tables
    for table in soup.find_all("table"):
        table_data = []
        for row in table.find_all("tr"):
            row_data = []
            for cell in row.find_all(["td", "th"]):
                text = cell.get_text(strip=True)
                row_data.append(text)
            if row_data:
                table_data.append(row_data)
        if table_data:
            data["tables"].append(table_data)

    # Remove empty fields
    for key in data:
        if isinstance(data[key], list) and not data[key]:
            data[key] = []

    return data

async def scrape_full_website(url: str, max_pages: int = 50) -> dict:
    """Scrape entire website with internal link discovery"""
    try:
        # Get base page
        base_data = await scrape_single_page(url)
        if "error" in base_data:
            return base_data

        # Extract internal links
        internal_links = set()
        base_domain = urlparse(url).netloc
        
        for link_info in base_data.get("links", []):
            link_url = link_info["url"]
            if urlparse(link_url).netloc == base_domain:
                # Avoid self-links and fragments
                clean_link = link_url.split("#")[0]
                if clean_link != url and clean_link not in internal_links:
                    internal_links.add(clean_link)

        # Limit pages to prevent overload
        links_to_scrape = list(internal_links)[:max_pages-1]  # -1 for base page
        
        # Scrape each internal page
        pages = [base_data]
        for link in links_to_scrape:
            try:
                page_data = await scrape_single_page(link)
                if "error" not in page_data:
                    pages.append(page_data)
            except Exception as e:
                print(f"Error scraping {link}: {e}")
                continue

        return {
            "start_url": url,
            "total_pages": len(pages),
            "pages": pages,
            "scraped_at": str(asyncio.get_event_loop().time())
        }

    except Exception as e:
        return {"error": f"Failed to scrape website: {str(e)}"}

# ------------------- Endpoints ------------------- #
@app.post("/scrape")
@limiter.limit("5/minute")
async def scrape_endpoint(request: Request, payload: ScrapeRequest):
    """Scrape website - single page or full site"""
    try:
        # Detect if it's a full site scrape or single page
        if any(domain in payload.url.lower() for domain in ['.com', '.org', '.net', '.pk']):
            # Try full site scrape first
            result = await scrape_full_website(payload.url, max_pages=20)
        else:
            # Single page scrape
            result = await scrape_single_page(payload.url)
        
        return {"success": True, "data": result}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/chat")
@limiter.limit("10/minute")
async def chat_endpoint(request: Request, payload: ChatRequest):
    """AI chat with exact scraped data analysis"""
    if not payload.message:
        return {"success": False, "error": "Message is required"}
    
    try:
        # If scraped data provided, analyze it
        if payload.scraped_data:
            prompt = f"""You are an EXACT data analyst. Analyze the following scraped website data and answer the user's question PRECISELY.

SCRAPED DATA:
{payload.scraped_data}

USER QUESTION:
{payload.message}

RULES:
1. ONLY use the provided scraped data
2. Give EXACT answers from the data
3. If information not found, say: "This information is not available in the scraped data"
4. Be precise and factual
5. Do not guess or add external knowledge
6. For modification requests, find the exact content and modify it accurately

Answer:"""
        else:
            # General knowledge question
            prompt = f"""You are an expert AI assistant. Provide a detailed and accurate answer to this question.

QUESTION:
{payload.message}

Give a comprehensive and helpful answer."""

        response = await call_gemini(prompt)
        return {"success": True, "response": response}
    
    except Exception as e:
        return {"success": False, "error": f"AI analysis failed: {str(e)}"}

@app.post("/format")
@limiter.limit("3/minute")
async def format_endpoint(request: Request, req: FormatRequest):
    """Format scraped data into different formats"""
    try:
        if req.format_type and req.format_type.strip():
            user_prompt = f"""Convert the following scraped data into {req.format_type} format. Be EXACT and complete.

DATA:
{req.data}

Requirements:
- Create proper {req.format_type} structure
- Include all available fields
- Ensure data integrity
- Make it ready for import/use"""
        else:
            user_prompt = f"""Convert this scraped data into Shopify-compatible CSV format with EXACT columns.

DATA:
{req.data}

Required CSV columns:
- Title (product name)
- Description 
- Price (if available)
- SKU (if available)
- Stock (if available)
- Image URL (if available)

Create a proper CSV that can be imported directly into Shopify."""

        formatted_result = await call_gemini(user_prompt)
        return {"success": True, "formatted": formatted_result}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

# ------------------- Health & Test ------------------- #
@app.get("/")
def health():
    return {"status": "Backend live 🚀", "gemini": "connected"}

@app.get("/test")
def test():
    return {"message": "AI Scraper Backend Working", "version": "2.0"}

# ------------------- Local Run ------------------- #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True
    )
