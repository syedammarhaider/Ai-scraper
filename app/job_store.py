import uuid
import time
from typing import Dict, List, Any
from collections import defaultdict

# Simple in-memory job store
jobs = {}
stats = defaultdict(int)

def create_job(url: str) -> Dict[str, Any]:
    """Create a new job and return the job dict"""
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "url": url,
        "status": "pending",
        "created_at": time.time(),
        "completed_at": None,
        "success": None,
        "error": None,
        "data": None
    }
    jobs[job_id] = job
    stats["total_jobs"] += 1
    return job

def complete_job(job_id: str, success: bool, data: Any = None, error: str = None):
    """Mark a job as complete"""
    if job_id in jobs:
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["completed_at"] = time.time()
        jobs[job_id]["success"] = success
        jobs[job_id]["data"] = data
        jobs[job_id]["error"] = error
        
        if success:
            stats["successful_jobs"] += 1
        else:
            stats["failed_jobs"] += 1

def get_dashboard_stats() -> Dict[str, Any]:
    """Get dashboard statistics"""
    return {
        "total_jobs": stats["total_jobs"],
        "successful_jobs": stats["successful_jobs"],
        "failed_jobs": stats["failed_jobs"],
        "success_rate": (
            stats["successful_jobs"] / max(stats["total_jobs"], 1) * 100
        )
    }

def get_recent_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent jobs"""
    recent = sorted(
        jobs.values(),
        key=lambda x: x["created_at"],
        reverse=True
    )
    return recent[:limit]
