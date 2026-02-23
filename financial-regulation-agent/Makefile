# =============================================================================
# Makefile - Production Commands for Financial Regulation Agent
# =============================================================================

.PHONY: help scrape ingest all docker-up docker-down docker-logs docker-build clean test shell

# Default values (can be overridden from command line)
LIMIT ?= 20
YEAR  ?= All

# =============================================================================
# Help
# =============================================================================
help:
	@echo "══════════════════════════════════════════════════════════════"
	@echo "   Financial Regulation Agent - Production Commands"
	@echo "══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "make scrape          → Run all spiders"
	@echo "make scrape LIMIT=10 YEAR=2023"
	@echo "make scrape SPIDER=sec_speeches  → Run only one spider"
	@echo ""
	@echo "make ingest          → Run ingestion pipeline only"
	@echo "make ingest LIMIT=50"
	@echo ""
	@echo "make all             → Scrape + Ingest (full pipeline)"
	@echo "make count-db        → Show document count in vector store"
	@echo "make logs            → Follow app log (tail -f logs/agent.log)"
	@echo "make logs-list       → List log files and locations"
	@echo ""
	@echo "make docker-up       → Build & run everything in Docker"
	@echo "make docker-down     → Stop Docker containers"
	@echo "make docker-logs     → Follow logs"
	@echo ""
	@echo "make clean           → Remove scraped files and logs"
	@echo "make test            → Run tests"
	@echo ""
	@echo "Current defaults: LIMIT=$(LIMIT) | YEAR=$(YEAR)"
	@echo "══════════════════════════════════════════════════════════════"

# =============================================================================
# Local Commands
# =============================================================================
scrape:
	@echo "🕸️  Running spiders... LIMIT=$(LIMIT) YEAR=$(YEAR)$(if $(SPIDER), SPIDER=$(SPIDER),)"
	./run_all.sh --limit $(LIMIT) --year $(YEAR) $(if $(SPIDER),--spider $(SPIDER),)

ingest:
	@echo "📥 Running ingestion pipeline..."
	python3.11 ingestion/ingest_scraped_docs.py --limit $(LIMIT)

count-db:
	$(PYTHON) -c "from retrieval.vector_store import get_vector_store; vs = get_vector_store(); count = vs._collection.count(); print(f'📊 Total documents in vector store: {count}')"

# Follow main app log (Ctrl+C to stop). Scrapy uses ingestion/regcrawler/scrapy.log when scraping.
logs:
	@mkdir -p logs
	@echo "📜 Following logs/agent.log (Ctrl+C to stop). Scrapy: ingestion/regcrawler/scrapy.log"
	@tail -f logs/agent.log 2>/dev/null || tail -f logs/agent.jsonl 2>/dev/null || echo "No log file yet. Run the app or scrape first."

# List log files and where Scrapy writes when run from regcrawler
logs-list:
	@echo "Log locations:"
	@echo "  App/agent : logs/agent.log or logs/agent.jsonl"
	@echo "  Scrapy    : ingestion/regcrawler/scrapy.log (when running scrape)"
	@if [ -d logs ]; then echo ""; echo "Contents of logs/:"; ls -la logs/ 2>/dev/null || true; fi
	@if [ -f ingestion/regcrawler/scrapy.log ]; then echo ""; echo "Scrapy log (last 10 lines):"; tail -10 ingestion/regcrawler/scrapy.log; fi

all: scrape ingest
	@echo "🎉 Full pipeline (scrape + ingest) completed!"

chat:
	@echo "💬 Starting interactive chat with the agent..."
	python3.11 run_agent.py

web-dev:
	@echo "🌐 Starting Web Chat Interface (Development)..."
	./run_webapp.sh --dev

web:
	@echo "🌐 Starting Web Chat Interface (Production)..."
	./run_webapp.sh 
# =============================================================================
# Docker Commands
# =============================================================================
COMPOSE_FILE = -f docker/docker-compose.yml

docker-build:
	@echo "🐳 Building Docker images..."
	docker compose $(COMPOSE_FILE) build --no-cache

docker-up:
	@echo "🐳 Starting services in Docker..."
	docker compose $(COMPOSE_FILE) up --build -d

docker-down:
	@echo "🛑 Stopping Docker services..."
	docker compose $(COMPOSE_FILE) down

docker-logs:
	docker compose $(COMPOSE_FILE) logs -f agent

docker-shell:
	docker compose $(COMPOSE_FILE) exec agent bash

# =============================================================================
# Maintenance
# =============================================================================
clean:
	@echo "🧹 Cleaning generated files..."
	rm -rf data/scraped/*.json
	rm -rf logs/*.log
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Clean completed."

test:
	@echo "🧪 Running tests..."
	pytest tests/ -v --tb=short

# =============================================================================
# Quick aliases
# =============================================================================
shell:
	@echo "🐚 Opening shell in virtual environment..."
	@if [ -f ".venv/bin/activate" ]; then \
		source .venv/bin/activate && bash; \
	else \
		echo "Virtual environment not found. Run 'python3.11 -m venv .venv' first."; \
	fi

# Default target
.DEFAULT_GOAL := help