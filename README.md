# Financial Regulation Agent

**RAG + Agent system for analyzing Financial Regulations** from FOMC, Federal Reserve, SEC, Basel, CFTC, FDIC, FCA (UK), FinCEN, EDGAR, plus structured data (Treasury, SOFR, FRED, FFIEC).

Built with **LangGraph**, **LangChain**, **Scrapy**, **Chroma**, and **FastAPI**.

---

## Features

**Data Ingestion & Search**
- Multi-regulator document ingestion from FOMC, Federal Reserve, SEC (Enforcement, Rules, Speeches), Basel, CFTC, FDIC, FCA (UK), FinCEN, and EDGAR
- Hybrid retrieval combining BM25 and vector similarity with Cohere reranking
- Structured data support for US Treasury rates, SOFR, FRED, and FFIEC

**Corrective RAG (CRAG)**
- Retrieval quality assessment with confidence-based routing (correct, ambiguous, incorrect)
- Decompose-then-recompose processing to extract relevant content from noisy documents
- Graceful degradation with clarification prompts when retrieval quality is insufficient

**Agent Pipeline**
- Orchestrated LangGraph workflow: intent classification → metadata filter extraction → planning → routing → retrieval → CRAG gate → synthesis → critic validation
- Self-correcting validation loop: answers are verified against sources; invalid responses trigger planner refinement with feedback
- Conditional routing to RAG, structured extraction, calculation tools, or direct response

**Operations & Security**
- API key authentication and rate limiting on all query endpoints
- LangSmith tracing for observability and debugging
- Docker-based deployment with health checks
- Configurable runtime filters (limit, year, spider) for ingestion pipelines
- Local CI parity: `make ci` runs lint, test, and security checks

---

## Agent Flow

<img src="langgraph.png" alt="LangGraph Architecture" width="1200" />

---

## Quick Start

### Option 1: Local Development

```bash
# 1. Setup
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env with your API keys

# 3. Run full pipeline (example with limit)
make scrape LIMIT=10

# 4. Ingest into vector DB
make ingest

# 5. Start FastAPI server
uvicorn app.main:api --reload --port 8000
```

### Option 2: Docker (Recommended for Production)
```bash
# Build and start everything
make docker-up

# View logs
make docker-logs

# Stop services
make docker-down

```

### Environment Variables (.env)
```bash
cp .env.example .env
# Edit .env with your values. Key variables:

# Required (depending on LLM_PROVIDER)
OPENAI_API_KEY=sk-...              # When using openai
GOOGLE_API_KEY=...                 # When using gemini

# Required for hybrid search reranking
COHERE_API_KEY=...

# Optional but recommended
LANGCHAIN_API_KEY=...              # LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=financial-regulation-agent

# Required for API access
API_KEY=your-super-secret-key      # Generate with: openssl rand -hex 32

# Model config (see .env.example for full list)
LLM_PROVIDER=gemini                # or openai
GEMINI_LLM_MODEL=gemini-2.5-pro
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
```

### API Usage
All requests require API key authentication.
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-super-secret-api-key-2026" \
  -d '{"query": "What did the FOMC say about interest rates in 2023?"}'
```

### Available Make Commands
```bash
make help                  # Show all commands

# Scraping (scrape also ingests; use make ingest for re-ingest only)
make scrape                # Run all spiders + ingest
make scrape SPIDER=fomc LIMIT=10 YEAR=2024
make spiders               # List spider names

# Ingestion
make ingest                # Ingest only (existing data/scraped/*.json)
make ingest-structured      # Treasury, SOFR, FRED, FFIEC → Chroma
make all                   # Full pipeline: scrape + ingest

# Utilities
make count-db              # Doc counts by regulator, type, spider
make check-db              # Chroma health: count, peek, similarity test
make diagnose-db           # Sample metadata inspection
make logs                  # Tail agent log
make logs-list             # Log locations + Scrapy tail

# Chat / Web
make chat                  # Interactive CLI chat
make web-dev               # Web UI (dev, auto-reload)
make web                   # Web UI (production)

# Evaluation
make benchmark             # Full benchmark (benchmark_questions.json)
make evaluate              # Single query evaluation (FOMC example)

# Docker
make docker-build          # Build agent + Chroma images
make docker-up             # Start containers
make docker-down           # Stop containers
make docker-logs           # Follow agent logs
make docker-shell          # Bash in agent container

# Maintenance
make ci                    # Run all CI checks locally (lint, test, security)
make langgraph-png         # Regenerate langgraph.png
make clean                 # clean-scraped + clean-logs + clean-cache
make clean-scraped         # Remove data/scraped/*.json
make clean-logs            # Remove logs/*
make clean-cache           # Remove __pycache__, httpcache, etc.
make clean-db              # Chroma collections (interactive)
make test                  # Run pytest
make shell                 # Bash with venv
```

### How to Run tests (example):
```bash
Run only end-to-end agent tests:
pytest tests/test_agent.py -v

Run with coverage:
pytest tests/test_agent.py --cov=graph --cov-report=term-missing
```

### Running a Single Spider
If you need to debug a specific source (like the SEC) or only need data from one regulator, run the spider directly from the crawler directory. Note: Settings like User-Agent and Delays are managed automatically in settings.py.

```bash
Navigate to the crawler project:
cd ingestion/regcrawler

Run a single spider (e.g., SEC Speeches) -a passes arguments to the spider:
PYTHONPATH="../../" scrapy crawl sec_speeches -a year=2024 -a limit=10
```

| Source | Spider Name | Output File (Default) |
| :--- | :--- | :--- |
| FOMC | `fomc` | `data/scraped/fomc.json` |
| Federal Reserve | `fed_reserve` | `data/scraped/fed_reserve.json` |
| FDIC | `fdic` | `data/scraped/fdic.json` |
| FCA (UK) | `fca` | `data/scraped/fca.json` |
| FinCEN | `fincen` | `data/scraped/fincen.json` |
| SEC Speeches | `sec_speeches` | `data/scraped/sec_speeches.json` |
| SEC Rules | `sec_rules` | `data/scraped/sec_rules.json` |
| SEC Enforcement | `sec_enforcement` | `data/scraped/sec_enforcement.json` |
| CFTC Enforcement | `cftc_enforcer` | `data/scraped/cftc_enforcer.json` |
| Basel (PDFs) | `basel_pdf` | `data/scraped/basel_pdf.json` |
| EDGAR Filings | `edgar_filings` | `data/scraped/edgar_filings.json` |

**Structured data** (via `make ingest-structured`): US Treasury rates, SOFR (NY Fed), FRED economic data, FFIEC Call Report data.