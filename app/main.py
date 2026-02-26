# app/main.py
"""
Final Production FastAPI Entry Point for Financial Regulation Agent
"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from graph.builder import app as graph_app
from observability.logger import log_error, log_info
from observability.monitor import SystemMonitor

from .config import Config, setup_environment
from .dependencies import APIKeyDep, QueryDep, RequestIDDep

setup_environment()

limiter = Limiter(key_func=get_remote_address, default_limits=[Config.RATE_LIMIT])

# Create FastAPI application
api = FastAPI(
    title="Financial Regulation Agent",
    description="Production RAG + Agent system for FOMC, SEC, Basel, CFTC & EDGAR",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
api.add_middleware(SlowAPIMiddleware)

# CORS Middleware
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/health")
async def health_check():
    """Health check endpoint with system metrics"""
    health_data = SystemMonitor.get_system_health()
    log_info("Health check called")
    return {
        "status": health_data["status"],
        "service": "financial-regulation-agent",
        "version": "1.0.0",
        "system": health_data,
    }


@api.post("/query")
@limiter.limit(Config.RATE_LIMIT)
async def process_query(request: Request, query: QueryDep, api_key: APIKeyDep, request_id: RequestIDDep):
    """
    Main query endpoint with streaming response.
    Requires valid X-API-Key header.
    """
    start_time = time.perf_counter()
    SystemMonitor.record_active_requests(1)

    log_info("Query received", query_preview=query[:100])

    async def stream_response():
        try:
            async for event in graph_app.astream_events({"query": query}, version="v2"):
                if event["event"] == "on_chain_stream":
                    chunk = event["data"].get("chunk", "")
                    if chunk:
                        yield f"data: {chunk}\n\n"

                elif event["event"] == "on_chain_end":
                    yield "data: [DONE]\n\n"

        except Exception as e:
            log_error("Streaming error occurred", error=str(e))
            SystemMonitor.record_error()
            yield "data: An error occurred while processing your query.\n\n"

        finally:
            latency = time.perf_counter() - start_time
            SystemMonitor.record_response_time(latency)
            SystemMonitor.record_active_requests(0)

    return StreamingResponse(stream_response(), media_type="text/event-stream")


@api.get("/")
async def root():
    """Root endpoint"""
    log_info("Root endpoint accessed")
    return {
        "message": "Financial Regulation Agent API is running",
        "docs": "/docs",
        "health": "/health",
    }


# Startup event
@api.on_event("startup")
async def startup_event():
    log_info("Financial Regulation Agent started successfully")
    log_info("API Key authentication enabled")
    log_info("Observability & monitoring fully initialized")
    log_info("Ready to accept requests on /query")
