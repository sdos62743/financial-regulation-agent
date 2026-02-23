# docker/Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANGCHAIN_TRACING_V2=true \
    LANGCHAIN_PROJECT=financial-regulation-agent

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Create necessary directories
RUN mkdir -p data/scraped data/basel_pdfs data/chroma_db logs

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with Uvicorn (production settings)
CMD ["uvicorn", "app.main:api", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]