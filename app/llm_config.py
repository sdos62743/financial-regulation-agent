# app/llm_config.py
"""
Central LLM & Embeddings Configuration - 2026 v4.x Compatible
"""

import os
from functools import lru_cache
from typing import Literal

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from observability.logger import log_info, log_error

# Force ChromaDB to stay silent
os.environ["ANONYMIZED_TELEMETRY"] = "False" 

# Provider selection via environment
LLM_PROVIDER: Literal["openai", "gemini"] = os.getenv("LLM_PROVIDER", "gemini").lower()

def sanitize_gemini_name(name: str) -> str:
    """Strips 'models/' prefix to prevent double-prefixing."""
    if not name:
        return ""
    return name.strip().replace("models/", "")


@lru_cache(maxsize=1)
def get_llm():
    """Returns a configured LLM instance."""
    timeout = float(os.getenv("LLM_TIMEOUT", "30.0"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

    if LLM_PROVIDER == "gemini":
        raw_model = os.getenv("GEMINI_LLM_MODEL", "gemini-1.5-flash")
        model_name = sanitize_gemini_name(raw_model)
        
        log_info(f"🔹 Initializing Gemini ({model_name})")

        # ==================== OLD CODE (Commented) ====================
        # return llm = ChatGoogleGenerativeAI(   # ← This was causing SyntaxError
        # =================================================================

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            api_version="v1",  # Force v1 (production) for paid tier
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.0,
            max_tokens=2048,
            timeout=60,
            max_retries=2,
            convert_system_message_to_human=True,            
        )
        return llm

    else:  # OpenAI
        model_name = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
        log_info(f"🔹 Initializing OpenAI ({model_name})")
        
        return ChatOpenAI(
            model=model_name,
            temperature=0.0,
            max_tokens=2000,
            timeout=timeout,
            max_retries=max_retries,
            convert_system_message_to_human=True,
        )


@lru_cache(maxsize=1)
def get_embeddings():
    """Returns the embeddings model."""
    if LLM_PROVIDER == "gemini":
        raw_name = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
        model_name = sanitize_gemini_name(raw_name)
        
        log_info(f"🔹 Initializing Gemini Embeddings: {model_name}")
        
        return GoogleGenerativeAIEmbeddings(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            client_options={"api_endpoint": "https://generativelanguage.googleapis.com"},
        )
    else:
        model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        log_info(f"🔹 Initializing OpenAI Embeddings: {model_name}")
        return OpenAIEmbeddings(model=model_name)


print(f"🔹 LLM Provider: {LLM_PROVIDER.upper()} initialized successfully")