#!/usr/bin/env python3
"""
Server - Tier 1 Production Web Gateway
Corrected imports to point to webapp/retrieval/query_controller.py.
"""

import os
import time

from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv(override=True)

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Core App Config
from app.config import Config, setup_environment
from app.dependencies import APIKeyDep, get_request_context

# Observability
from observability.logger import log_error, log_info
from observability.monitor import SystemMonitor

# FIXED: Reverted to your specific path structure
from webapp.retrieval.query_controller import RAGController

# 2. Initialize Environment
setup_environment()

# 3. App Initialization
limiter = Limiter(key_func=get_remote_address, default_limits=[Config.RATE_LIMIT])
app = FastAPI(
    title="Financial Regulation Intelligence Terminal",
    description="Tier 1 RAG Agent for FOMC, SEC, Basel, CFTC & EDGAR",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# 4. Middleware
# Request logging middleware - runs before routes/deps, so we see all incoming requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    log_info(f"📨 Incoming: {request.method} {request.url.path}")
    response = await call_next(request)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Static Assets
# Points to webapp/static
STATIC_DIR = os.path.join(os.getcwd(), "webapp", "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 6. Global Controller
controller = RAGController()


class ChatInput(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    thread_id: str = Field(default="default_session")


# 7. Routes
@app.get("/", response_class=HTMLResponse)
async def serve_chat_ui():
    """Serve the terminal web interface."""
    try:
        index_path = os.path.join(STATIC_DIR, "index.html")
        with open(index_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log_error(f"UI index.html missing at {index_path}")
        return HTMLResponse(
            "<h1>System Error</h1><p>Terminal UI assets not found.</p>", status_code=404
        )


@app.get("/health")
async def health_check():
    return SystemMonitor.get_system_health()


@app.post("/ask")
@limiter.limit(Config.RATE_LIMIT)
async def ask_rag(
    request: Request,
    data: ChatInput,
    _auth: APIKeyDep,
    request_id: str = Depends(get_request_context),
):
    start_time = time.perf_counter()

    try:
        log_info(f"📥 [Web] Request: {data.thread_id} | ID: {request_id}")

        result = await controller.ask(data.query, thread_id=data.thread_id)

        if not result or result.get("success") is False:
            error_msg = result.get("error", "Unknown Graph Error")
            log_error(f"❌ [Web] Graph failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        raw_docs = result.get("documents", [])
        parsed_sources = []
        for doc in raw_docs:
            meta = getattr(doc, "metadata", doc if isinstance(doc, dict) else {})
            parsed_sources.append(
                {
                    "title": meta.get("title")
                    or meta.get("source")
                    or "Regulatory Document",
                    "page": meta.get("page", "N/A"),
                }
            )

        latency = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "answer": result.get("answer") or result.get("synthesized_response"),
            "sources": parsed_sources,
            "thread_id": data.thread_id,
            "latency_ms": latency,
            "request_id": request_id,
        }

    except Exception as e:
        log_error(f"💥 [Web] Critical failure: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "answer": "### Internal Server Error\nCheck server logs.",
                "thread_id": data.thread_id,
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webapp.server:app", host="0.0.0.0", port=8000, reload=True)
