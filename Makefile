# =============================================================================
# Makefile - Financial Regulation Agent (Production Grade)
# =============================================================================

.PHONY: help scrape ingest ingest-structured all docker-up docker-down \
        docker-logs docker-build docker-shell clean test shell spiders \
        logs logs-list chat web web-dev count-db

# Optional parameters (passed only if explicitly set)
LIMIT  ?=
YEAR   ?=
SPIDER ?=

# All available spiders (must match Scrapy spider names exactly)
SPIDERS := basel_pdf cftc_enforcer edgar_filings fca fdic fed_reserve fincen \
           fomc sec_enforcement sec_rules sec_speeches

# =============================================================================
# Help
# =============================================================================
help:
	@echo "══════════════════════════════════════════════════════════════"
	@echo "   Financial Regulation Agent - Run Commands"
	@echo "══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "Scraping:"
	@echo "  make scrape"
	@echo "  make scrape SPIDER=fomc"
	@echo "  make scrape LIMIT=10"
	@echo "  make scrape YEAR=2024"
	@echo "  make scrape SPIDER=basel_pdf LIMIT=5 YEAR=2023"
	@echo ""
	@echo "Ingestion:"
	@echo "  make ingest"
	@echo "  make ingest-structured"
	@echo ""
	@echo "Full Pipeline:"
	@echo "  make all"
	@echo ""
	@echo "Utilities:"
	@echo "  make spiders"
	@echo "  make count-db"
	@echo "  make logs"
	@echo "  make logs-list"
	@echo ""
	@echo "Chat / Web:"
	@echo "  make chat"
	@echo "  make web-dev"
	@echo "  make web"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build"
	@echo "  make docker-up"
	@echo "  make docker-down"
	@echo "  make docker-logs"
	@echo "  make docker-shell"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean"
	@echo "  make test"
	@echo "  make shell"
	@echo "══════════════════════════════════════════════════════════════"

# =============================================================================
# Scraping
# =============================================================================
scrape:
	@echo "🕸️  Running spiders..."
	./run_all.sh \
	$(if $(LIMIT),--limit $(LIMIT),) \
	$(if $(YEAR),--year $(YEAR),) \
	$(if $(SPIDER),--spider $(SPIDER),)

spiders:
	@echo "Available spiders:"
	@for s in $(SPIDERS); do echo "  $$s"; done
	@echo ""
	@echo "Example: make scrape SPIDER=fomc LIMIT=10 YEAR=2024"

# =============================================================================
# Ingestion
# =============================================================================
ingest:
	@echo "📥 Running ingestion pipeline..."
	python3.11 ingestion/ingest_scraped_docs.py

ingest-structured:
	@echo "📥 Ingesting structured data (Treasury, SOFR, FRED, FFIEC)..."
	python3.11 ingestion/regcrawler/regcrawler/structured_data/structured_data_ingest.py

count-db:
	@python3.11 -c "from retrieval.vector_store import get_vector_store; vs=get_vector_store(); print(f'📊 Total documents in vector store: {vs._collection.count()}')"

all: scrape ingest
	@echo "🎉 Full pipeline completed."

# =============================================================================
# Logs
# =============================================================================
logs:
	@mkdir -p logs
	@echo "📜 Following logs/agent.log (Ctrl+C to stop)"
	@tail -f logs/agent.log 2>/dev/null || \
	tail -f logs/agent.jsonl 2>/dev/null || \
	echo "No log file yet."

logs-list:
	@echo "Log locations:"
	@echo "  App / Agent logs : logs/agent.log or logs/agent.jsonl"
	@echo "  Scrapy logs      : ingestion/regcrawler/scrapy.log"
	@echo ""
	@if [ -d logs ]; then \
		echo "Contents of logs/:"; \
		ls -la logs/; \
	fi
	@if [ -f ingestion/regcrawler/scrapy.log ]; then \
		echo ""; \
		echo "Last 10 lines of Scrapy log:"; \
		tail -10 ingestion/regcrawler/scrapy.log; \
	fi

# =============================================================================
# Chat / Web
# =============================================================================
chat:
	@echo "💬 Starting interactive chat..."
	python3.11 run_agent.py

web-dev:
	@echo "🌐 Starting Web Interface (Development)..."
	./run_webapp.sh --dev

web:
	@echo "🌐 Starting Web Interface (Production)..."
	./run_webapp.sh

# =============================================================================
# Docker
# =============================================================================
COMPOSE_FILE = -f docker/docker-compose.yml

docker-build:
	@echo "🐳 Building Docker images..."
	docker compose $(COMPOSE_FILE) build --no-cache

docker-up:
	@echo "🐳 Starting Docker services..."
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
	rm -rf data/scraped/*
	rm -rf logs/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Clean completed."

test:
	@echo "🧪 Running tests..."
	pytest tests/ -v --tb=short

shell:
	@echo "🐚 Opening virtual environment shell..."
	@if [ -f ".venv/bin/activate" ]; then \
		source .venv/bin/activate && bash; \
	else \
		echo "Virtual environment not found. Run: python3.11 -m venv .venv"; \
	fi

.DEFAULT_GOAL := help