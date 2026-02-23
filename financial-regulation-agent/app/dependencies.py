#!/usr/bin/env python3
"""
Production Dependencies - Tier 1 Optimized
Handles authentication, context propagation, and validation.
"""

import os
import uuid
from typing import Annotated, Generator, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import Config
from observability.logger import log_info, log_warning
from observability.tracer import RequestTracer


# ----------------------------------------------------------------------
# Schema Validation
# ----------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="The user's natural language query")


# ----------------------------------------------------------------------
# Context & Tracing (Crucial for Tier 1 Log Correlation)
# ----------------------------------------------------------------------
async def get_request_context(request: Request) -> str:
    """
    Extracts or generates a Request ID and initializes the Tracer.
    Ensures that every log from this request is correlated.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    
    # Set the global context for this thread/task
    RequestTracer.set_request_id(request_id)
    
    log_info(f"📥 [API] Request started | Path: {request.url.path} | ID: {request_id}")
    return request_id


# ----------------------------------------------------------------------
# API Key Authentication
# ----------------------------------------------------------------------
def validate_api_key(
    request: Request,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None
) -> str:
    """
    Validates API key using centralized Config.
    """
    # Fallback to env check if Config isn't populated
    expected_key = os.getenv("API_KEY") 

    if not expected_key:
        log_warning("⚠️ API_KEY not configured on server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Server configuration error"
        )

    if not x_api_key or x_api_key != expected_key:
        log_warning(f"🚫 Unauthorized access attempt from: {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or missing API key"
        )

    return x_api_key


# ----------------------------------------------------------------------
# Database Placeholder
# ----------------------------------------------------------------------
def get_db_session() -> Generator[None, None, None]:
    """Placeholder for future database integration (Feedback/History)."""
    yield None


# ----------------------------------------------------------------------
# Annotated Types for Routes
# ----------------------------------------------------------------------
# Use these in your controllers for clean, readable code
TraceDep = Annotated[str, Depends(get_request_context)]
APIKeyDep = Annotated[str, Depends(validate_api_key)]
DBSessionDep = Annotated[None, Depends(get_db_session)]