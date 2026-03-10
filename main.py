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

# ------------------- App Imports ------------------- #
from app.job_store import (
    create_job,
    complete_job,
    get_dashboard_stats,
    get_recent_jobs,
)
from app.scraper import scrape_full_website
from app.gemini_client import call_gemini

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

# ------------------- Background Job Helper ------------------- #
async def run_crawler_job(job_id: int, url: str):
    try:
        data = await scrape_full_website(url)
        complete_job(job_id, success=True, data=data)
    except Exception as e:
        complete_job(job_id, success=False, error=str(e))

# ------------------- Endpoints ------------------- #
@app.post("/scrape")
@limiter.limit("5/minute")
async def scrape_endpoint(request: Request, payload: ScrapeRequest):
    job = create_job(payload.url)  # returns the full job dict
    try:
        data = await scrape_full_website(payload.url)
        # mark job complete (don't pass data unless job_store supports it)
        complete_job(job, success=True)
        return {"success": True, "data": data}
    except Exception as e:
        complete_job(job, success=False, error=str(e))
        return {"success": False, "error": str(e)}

@app.post("/format")
@limiter.limit("3/minute")
async def format_endpoint(request: Request, req: FormatRequest):
    try:
        if req.format_type and req.format_type.strip():
            user_prompt = f"{req.data}\n\nConvert this into {req.format_type} format."
        else:
            user_prompt = (
                f"{req.data}\n\nConvert this scraped data into a Shopify-compatible CSV format "
                "(columns: Title, Description, Price, SKU, Stock, Image URL)"
            )

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
    return {"message": "Hello from FastAPI", "version": "2.0"}

# ------------------- Dashboard ------------------- #
@app.get("/dashboard/stats")
def dashboard_stats():
    return get_dashboard_stats()

@app.get("/dashboard/jobs")
def dashboard_jobs():
    return get_recent_jobs()

# ------------------- Local Run ------------------- #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",  # adjust if using app.main:app for module structure
        host="0.0.0.0",
        port=PORT,
        reload=True
    )
