# =============================================================================
# Makefile - Financial Regulation Agent (Production Grade)
# =============================================================================

.PHONY: help scrape ingest ingest-structured all docker-up docker-down \
        docker-logs docker-build docker-shell clean clean-scraped clean-logs clean-cache clean-db check-db diagnose-db test shell spiders \
        logs logs-list chat web web-dev count-db benchmark evaluate langgraph-png ci

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
# help: Print available commands and usage (default target)
help:
	@echo "══════════════════════════════════════════════════════════════"
	@echo "   Financial Regulation Agent - Run Commands"
	@echo "══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "Scraping:"
	@echo "  make scrape              # Scrape + ingest (run spiders, then load into Chroma)"
	@echo "  make scrape SPIDER=fomc  # Scrape single spider + ingest"
	@echo "  make scrape LIMIT=10     # Limit items per spider"
	@echo "  make spiders             # List spider names"
	@echo ""
	@echo "Ingestion:"
	@echo "  make ingest              # Ingest only (re-run on existing data/scraped/*.json)"
	@echo "  make ingest-structured   # Treasury, SOFR, FRED, FFIEC → Chroma"
	@echo ""
	@echo "Full Pipeline:"
	@echo "  make all                 # scrape + ingest"
	@echo ""
	@echo "Utilities:"
	@echo "  make count-db            # Doc counts by regulator, type, spider"
	@echo "  make check-db            # Chroma health: count, peek 5 docs, similarity test"
	@echo "  make diagnose-db        # Chroma metadata + CFTC sample inspection"
	@echo "  make logs               # Tail agent log"
	@echo "  make logs-list           # Log locations + Scrapy tail"
	@echo ""
	@echo "Chat / Web:"
	@echo "  make chat                # Interactive CLI chat"
	@echo "  make web-dev             # Web UI (dev, auto-reload)"
	@echo "  make web                 # Web UI (production)"
	@echo ""
	@echo "Evaluation:"
	@echo "  make benchmark           # Run full benchmark (evaluation/benchmark_questions.json)"
	@echo "  make evaluate            # Evaluate single query (FOMC interest rates)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build        # Build agent + Chroma images"
	@echo "  make docker-up           # Start containers"
	@echo "  make docker-down         # Stop containers"
	@echo "  make docker-logs         # Follow agent logs"
	@echo "  make docker-shell        # Bash in agent container"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean               # clean-scraped + clean-logs + clean-cache"
	@echo "  make clean-scraped       # data/scraped/*.json"
	@echo "  make clean-logs          # logs/*"
	@echo "  make clean-cache         # __pycache__, .pyc, httpcache, debug html"
	@echo "  make clean-db            # Chroma collections (interactive)"
	@echo "  make test                # Run pytest"
	@echo "  make ci                  # Run all CI checks locally (lint, test, security)"
	@echo "  make langgraph-png       # Regenerate langgraph.png (requires network)"
	@echo "  make shell               # Bash with venv"
	@echo "══════════════════════════════════════════════════════════════"

# =============================================================================
# Scraping
# =============================================================================
# scrape: Run Scrapy spiders + ingest into Chroma (scrape then ingest in one go).
#         Use make ingest only if you already have scraped JSON and want to re-ingest.
#         Optional: SPIDER=name LIMIT=N YEAR=YYYY
scrape:
	@echo "🕸️  Running spiders..."
	./run_all.sh \
	$(if $(LIMIT),--limit $(LIMIT),) \
	$(if $(YEAR),--year $(YEAR),) \
	$(if $(SPIDER),--spider $(SPIDER),)

# spiders: List all available spider names for use with make scrape SPIDER=name
spiders:
	@echo "Available spiders:"
	@for s in $(SPIDERS); do echo "  $$s"; done
	@echo ""
	@echo "Example: make scrape SPIDER=fomc LIMIT=10 YEAR=2024"

# =============================================================================
# Ingestion
# =============================================================================
# ingest: Ingest only — load existing data/scraped/*.json, chunk, embed, store in Chroma
#         (Use when you have scraped files and want to re-ingest without re-scraping.)
ingest:
	@echo "📥 Running ingestion pipeline..."
	python3.11 ingestion/ingest_scraped_docs.py

# ingest-structured: Fetch Treasury rates, SOFR, Fed Funds (FRED), FFIEC; embed into Chroma
ingest-structured:
	@echo "📥 Ingesting structured data (Treasury, SOFR, FRED, FFIEC)..."
	python3.11 ingestion/regcrawler/regcrawler/structured_data/structured_data_ingest.py

# count-db: Show total docs and counts by regulator, source_type, type, spider
count-db:
	@python3.11 scripts/count_db.py

# check-db: Chroma health check — total count, peek last 5 metadata entries,
#           and test similarity search for "Basel" (verifies embeddings + retrieval)
check-db:
	@echo "🔍 Chroma health check..."
	@python3.11 scripts/check_db.py

# diagnose-db: Inspect sample document metadata in Chroma + CFTC-specific check (for debugging ingestion)
diagnose-db:
	@echo "🔍 Chroma metadata diagnostic..."
	@python3.11 scripts/diagnose_chroma.py
	@echo ""
	@echo "🔍 CFTC document check..."
	@python3.11 scripts/check_cftc.py

# all: Full pipeline — scrape all spiders, then ingest into vector store
all: scrape ingest
	@echo "🎉 Full pipeline completed."

# =============================================================================
# Logs
# =============================================================================
# logs: Tail agent log file (logs/agent.log or logs/agent.jsonl)
logs:
	@mkdir -p logs
	@echo "📜 Following logs/agent.log (Ctrl+C to stop)"
	@tail -f logs/agent.log 2>/dev/null || \
	tail -f logs/agent.jsonl 2>/dev/null || \
	echo "No log file yet."

# logs-list: Show log file locations and last lines of Scrapy log
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
# chat: Interactive CLI chat with the agent
chat:
	@echo "💬 Starting interactive chat..."
	python3.11 scripts/run_agent.py

# benchmark: Run full benchmark evaluation on benchmark_questions.json
benchmark:
	@echo "🏆 Running benchmark evaluation..."
	python3.11 scripts/run_benchmark.py

# evaluate: Evaluate single query (FOMC interest rates example)
evaluate:
	@echo "📊 Evaluating single query..."
	python3.11 scripts/evaluate_single.py

# web-dev: Start web UI with auto-reload for development
web-dev:
	@echo "🌐 Starting Web Interface (Development)..."
	./run_webapp.sh --dev

# web: Start web UI in production mode
web:
	@echo "🌐 Starting Web Interface (Production)..."
	./run_webapp.sh

# =============================================================================
# Docker
# =============================================================================
COMPOSE_FILE = -f docker/docker-compose.yml
export PROJECT_ROOT := $(CURDIR)

# docker-build: Build agent + Chroma images (no cache)
docker-build:
	@echo "🐳 Building Docker images..."
	docker compose $(COMPOSE_FILE) build --no-cache

# docker-up: Build and start agent + Chroma in background
docker-up:
	@echo "🐳 Starting Docker services..."
	docker compose $(COMPOSE_FILE) up --build -d

# docker-down: Stop and remove containers
docker-down:
	@echo "🛑 Stopping Docker services..."
	docker compose $(COMPOSE_FILE) down

# docker-logs: Follow agent container logs
docker-logs:
	docker compose $(COMPOSE_FILE) logs -f agent

# docker-shell: Open bash shell in agent container
docker-shell:
	docker compose $(COMPOSE_FILE) exec agent bash

# =============================================================================
# Maintenance
# =============================================================================
# clean: Remove scraped JSON, logs, cache/temp (keeps Chroma DB)
clean: clean-scraped clean-logs clean-cache
	@echo "✅ Clean completed."

# clean-scraped: Remove scraped JSON files from data/scraped/
clean-scraped:
	@echo "🧹 Cleaning scraped files (data/scraped/*.json)..."
	rm -rf data/scraped/*
	@echo "✅ Scraped files cleaned."

# clean-logs: Remove agent log files from logs/
clean-logs:
	@echo "🧹 Cleaning logs (logs/*)..."
	rm -rf logs/*
	@echo "✅ Logs cleaned."

# clean-cache: Remove __pycache__, .pyc, Scrapy httpcache, debug html (not json, not logs)
clean-cache:
	@echo "🧹 Cleaning cache and temp files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf ingestion/regcrawler/httpcache 2>/dev/null || true
	rm -f ingestion/regcrawler/basel_debug*.html ingestion/regcrawler/basel_last_run.html 2>/dev/null || true
	@echo "✅ Cache cleaned."

# clean-db: Interactive Chroma cleanup — list collections, delete by name or all
clean-db:
	@echo "🗑️  Chroma vector DB cleanup (interactive)..."
	python3.11 scripts/clean_chroma.py

# test: Run pytest suite
test:
	@echo "🧪 Running tests..."
	pytest tests/ -v --tb=short

# ci: Run all CI checks locally (lint, test, security) - mirrors .github/workflows/ci.yml
ci:
	@chmod +x scripts/run_ci_checks.sh
	@./scripts/run_ci_checks.sh all

# langgraph-png: Regenerate langgraph.png (script is local-only, not in repo)
langgraph-png:
	@if [ -f scripts/generate_langgraph_png.py ]; then \
		echo "📊 Generating langgraph.png..."; \
		python3.11 scripts/generate_langgraph_png.py; \
	else \
		echo "⚠️ scripts/generate_langgraph_png.py not found (local-only)"; \
	fi

# shell: Open bash with venv activated
shell:
	@echo "🐚 Opening virtual environment shell..."
	@if [ -f ".venv/bin/activate" ]; then \
		source .venv/bin/activate && bash; \
	else \
		echo "Virtual environment not found. Run: python3.11 -m venv .venv"; \
	fi

.DEFAULT_GOAL := help