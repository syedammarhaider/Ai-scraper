from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from groq import Groq
from scraper import UltraScraper, ProgressTracker
import os
import json
import time
import uuid
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Load .env variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(title="Ultra Professional AI Scraper", version="4.0")
templates = Jinja2Templates(directory="templates")
scraper = UltraScraper()

# Create downloads directory
os.makedirs("downloads", exist_ok=True)

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

# ---------- GROQ AI INITIALIZATION ----------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
MODEL_DEEP = "llama-3.3-70b-versatile"

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Store active scraping sessions
active_scrapes = {}


# ---------- HOME PAGE ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main homepage"""
    return templates.TemplateResponse("index.html", {"request": request})


# ---------- HEALTH CHECK ----------
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "4.0"
    }


# ---------- FULL WEBSITE SCRAPE ----------
@app.post("/scrape-full-website")
async def scrape_full_website(request: Request):
    """
    Scrape ALL products from an entire website
    Uses BFS crawling algorithm to find and extract all products
    """
    form = await request.form()
    url = form.get("url")
    max_pages = int(form.get("max_pages", 500))
    
    if not url:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "URL is required"}
        )
    
    # Ensure URL has protocol
    if not url.startswith("http"):
        url = "https://" + url
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    # Start scraping in background thread
    future = executor.submit(
        run_full_scrape,
        session_id,
        url,
        max_pages
    )
    
    # Store future for progress tracking
    active_scrapes[session_id] = {
        "future": future,
        "url": url,
        "start_time": time.time(),
        "status": "starting",
        "progress": {
            "crawled": 0,
            "products_found": 0,
            "products_extracted": 0
        }
    }
    
    return {
        "success": True,
        "session_id": session_id,
        "message": f"Started full website scraping for {url}",
        "max_pages": max_pages
    }


def run_full_scrape(session_id: str, url: str, max_pages: int):
    """Run full website scrape in background thread"""
    def progress_callback(crawled: int, products_found: int):
        """Update progress during scraping"""
        if session_id in active_scrapes:
            active_scrapes[session_id]["progress"]["crawled"] = crawled
            active_scrapes[session_id]["progress"]["products_found"] = products_found
            active_scrapes[session_id]["status"] = "crawling"
    
    try:
        # Update status
        active_scrapes[session_id]["status"] = "crawling"
        
        # Run full website scrape
        result = scraper.scrape_full_website(
            start_url=url,
            max_pages=max_pages,
            progress_callback=progress_callback
        )
        
        # Update with extraction progress
        active_scrapes[session_id]["status"] = "extracting"
        active_scrapes[session_id]["progress"]["products_extracted"] = len(result.get("products", []))
        
        # Save results
        timestamp = int(time.time())
        json_path = scraper.save_as_json(result, f"full_website_{timestamp}")
        csv_path = scraper.save_as_csv(result, f"full_website_{timestamp}")
        excel_path = scraper.save_as_excel(result, f"full_website_{timestamp}")
        
        # Update final status
        active_scrapes[session_id].update({
            "status": "completed",
            "result": result,
            "files": {
                "json": json_path,
                "csv": csv_path,
                "excel": excel_path
            },
            "end_time": time.time()
        })
        
    except Exception as e:
        active_scrapes[session_id]["status"] = "failed"
        active_scrapes[session_id]["error"] = str(e)
        print(f"❌ Scrape failed for session {session_id}: {e}")


# ---------- SCRAPE PROGRESS ----------
@app.get("/scrape-progress/{session_id}")
async def get_scrape_progress(session_id: str):
    """Get progress of an ongoing full website scrape"""
    if session_id not in active_scrapes:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Session not found"}
        )
    
    session = active_scrapes[session_id]
    
    # Calculate elapsed time
    elapsed = time.time() - session["start_time"]
    
    response = {
        "success": True,
        "session_id": session_id,
        "status": session["status"],
        "url": session["url"],
        "elapsed_seconds": round(elapsed, 2),
        "progress": session.get("progress", {})
    }
    
    # Add result if completed
    if session["status"] == "completed" and "result" in session:
        response["result"] = {
            "total_pages": session["result"]["statistics"]["total_pages_crawled"],
            "total_products": session["result"]["statistics"]["total_products_extracted"],
            "success_rate": session["result"]["statistics"]["extraction_success_rate"]
        }
        response["files"] = session.get("files", {})
    
    # Add error if failed
    if session["status"] == "failed":
        response["error"] = session.get("error", "Unknown error")
    
    return response


# ---------- LEGACY SINGLE PAGE SCRAPE ----------
@app.post("/scrape")
async def scrape_single(request: Request):
    """Legacy single page scrape - kept for compatibility"""
    form = await request.form()
    url = form.get("url")
    mode = form.get("mode", "comprehensive")
    js = form.get("js", "false")

    if not url:
        return {"success": False, "error": "URL required"}

    if not url.startswith("http"):
        url = "https://" + url

    # For full website scrape, use new endpoint
    if mode == "full_website":
        return await scrape_full_website(request)

    # Single page scrape
    data = scraper.scrape_website(url, mode)

    if "error" in data:
        return {"success": False, "error": data["error"]}

    return {"success": True, "data": data, "session_id": str(uuid.uuid4())}


# ---------- GROQ AI CHAT (Scraped Data Only) ----------
@app.post("/groq-chat")
async def groq_chat(request: Request):
    """Chat with AI about scraped data only"""
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data")

    if not message or not scraped:
        return {"success": False, "error": "Missing message or scraped data"}

    try:
        data = json.loads(scraped)
    except:
        return {"success": False, "error": "Invalid scraped data format"}

    system_prompt = """
    You are an AI assistant that ONLY answers questions based on the provided scraped website data.
    
    RULES:
    1. ONLY use information from the scraped data provided below
    2. If the answer is not in the scraped data, say: "This information is not available in the scraped website data."
    3. Do NOT use any external knowledge or make up information
    4. Be concise and accurate
    5. If asked about products, provide details exactly as they appear in the data
    """

    # Prepare context (limit to avoid token limits)
    context = f"SCRAPED WEBSITE DATA:\n{json.dumps(data, indent=2, default=str)[:20000]}\n\n"
    context += f"USER QUESTION: {message}\n\n"
    context += "Answer based ONLY on the scraped data above:"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.1,  # Low temperature for factual responses
            max_tokens=1500
        )

        answer = response.choices[0].message.content
        if not answer:
            answer = "No response generated."

        return {"success": True, "response": answer.strip()}

    except Exception as e:
        return {"success": False, "error": f"Groq API error: {str(e)}"}


# ---------- GROK MODE (Universal Knowledge) ----------
@app.post("/grok-mode")
async def grok_mode(request: Request):
    """Universal AI chat - answers any question using AI knowledge"""
    if not client:
        return {"success": False, "error": "GROQ_API_KEY not set or invalid"}

    form = await request.form()
    message = form.get("message")
    scraped = form.get("scraped_data", "{}")
    analysis_type = form.get("analysis_type", "comprehensive")

    if not message:
        return {"success": False, "error": "Missing message"}

    system_prompt = """
    You are GROK MODE - An advanced AI with universal knowledge.
    
    CAPABILITIES:
    1. Answer ANY question using your comprehensive knowledge base
    2. Provide detailed, expert-level responses
    3. Be helpful, accurate, and thorough
    4. Format responses nicely with markdown when appropriate
    5. For product-related questions, provide detailed analysis
    6. For technical questions, explain concepts clearly
    """

    full_context = f"USER QUESTION: {message}\n\n"
    full_context += "Provide a comprehensive, detailed answer:"

    try:
        response = client.chat.completions.create(
            model=MODEL_DEEP,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_context}
            ],
            temperature=0.3,
            max_tokens=8000  # Allow long responses
        )

        answer = response.choices[0].message.content
        if not answer:
            answer = "No response generated."

        return {"success": True, "response": answer.strip(), "mode": "grok_mode"}

    except Exception as e:
        return {"success": False, "error": f"Grok Mode error: {str(e)}"}


# ---------- EXPORT DATA ----------
@app.post("/export")
async def export_data(request: Request):
    """Export scraped data in various formats"""
    body = await request.json()
    fmt = body.get("format")
    data = body.get("data")
    filename = body.get("filename", f"scraped_{int(time.time())}")

    if not fmt or not data:
        return {"success": False, "error": "Missing format or data"}

    try:
        # Parse data if it's a string
        if isinstance(data, str):
            data = json.loads(data)
    except:
        return {"success": False, "error": "Invalid data format"}

    # Export handlers
    handlers = {
        "json": scraper.save_as_json,
        "csv": scraper.save_as_csv,
        "excel": scraper.save_as_excel,
        "txt": scraper.save_as_text,
        "pdf": scraper.save_as_pdf,
        "markdown": save_as_markdown  # Custom function below
    }

    if fmt not in handlers:
        return {"success": False, "error": f"Unsupported format: {fmt}"}

    try:
        # Handle full website results differently
        if "products" in data:  # Full website scrape result
            filepath = handlers[fmt](data, filename)
        else:  # Single page scrape result
            # Wrap in products format for compatibility
            wrapped_data = {
                "products": [data] if isinstance(data, dict) else data,
                "statistics": {
                    "total_products": 1
                }
            }
            filepath = handlers[fmt](wrapped_data, filename)

        return FileResponse(
            path=filepath,
            filename=os.path.basename(filepath),
            media_type="application/octet-stream"
        )

    except Exception as e:
        return {"success": False, "error": f"Export error: {str(e)}"}


def save_as_markdown(data: Dict, filename: str) -> str:
    """Save data as Markdown file"""
    downloads_dir = "downloads"
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
    
    filepath = os.path.join(downloads_dir, f"{filename}.md")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# Full Website Scraping Results\n\n")
        f.write(f"**URL:** {data.get('start_url', 'N/A')}\n")
        f.write(f"**Date:** {data.get('crawled_at', 'N/A')}\n")
        f.write(f"**Total Pages:** {data.get('statistics', {}).get('total_pages_crawled', 0)}\n")
        f.write(f"**Total Products:** {data.get('statistics', {}).get('total_products_extracted', 0)}\n\n")
        
        f.write("## Products\n\n")
        
        for idx, product in enumerate(data.get('products', []), 1):
            f.write(f"### {idx}. {product.get('name', 'Unknown')}\n")
            f.write(f"- **Price:** {product.get('price', 'N/A')} {product.get('currency', '')}\n")
            f.write(f"- **Brand:** {product.get('brand', 'N/A')}\n")
            f.write(f"- **SKU:** {product.get('sku', 'N/A')}\n")
            f.write(f"- **Categories:** {', '.join(product.get('categories', []))}\n")
            f.write(f"- **Rating:** {product.get('reviews', {}).get('rating', 'N/A')}/5 ({product.get('reviews', {}).get('count', '0')} reviews)\n")
            f.write(f"- **Availability:** {product.get('availability', 'N/A')}\n")
            f.write(f"- **URL:** {product.get('url', 'N/A')}\n\n")
            f.write(f"**Description:**\n{product.get('description', 'N/A')[:300]}...\n\n")
            f.write("---\n\n")
    
    return filepath


# ---------- CLEANUP OLD SESSIONS ----------
@app.on_event("startup")
async def startup_event():
    """Start background task to clean up old sessions"""
    asyncio.create_task(cleanup_old_sessions())


async def cleanup_old_sessions():
    """Remove sessions older than 1 hour"""
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        current_time = time.time()
        to_delete = []
        
        for session_id, session in active_scrapes.items():
            # Remove completed/failed sessions older than 1 hour
            if session.get("end_time") and current_time - session["end_time"] > 3600:
                to_delete.append(session_id)
            # Remove stuck sessions older than 2 hours
            elif current_time - session["start_time"] > 7200:
                to_delete.append(session_id)
        
        for session_id in to_delete:
            active_scrapes.pop(session_id, None)
            print(f"🧹 Cleaned up old session: {session_id}")


# ---------- RUN APP ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)