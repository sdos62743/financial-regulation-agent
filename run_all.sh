#!/usr/bin/env bash
# =============================================================================
# run_all.sh - Master Production Runner for Financial Regulation Agent
# =============================================================================

set -euo pipefail  # Exit on error, unset vars, pipeline failure

echo "🚀 Financial Regulation Agent - Master Runner"

# -----------------------------------------------------------------------------
# Runtime parameters (no hidden defaults)
# -----------------------------------------------------------------------------
LIMIT=""
YEAR=""
SPIDER=""
USE_DOCKER=false
CLEAR_DB=false

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --year)
            YEAR="$2"
            shift 2
            ;;
        --spider)
            SPIDER="$2"
            shift 2
            ;;
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --clear)
            CLEAR_DB=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_all.sh [--limit N] [--year YYYY] [--spider NAME] [--docker] [--clear]"
            exit 0
            ;;
        *)
            echo "❌ Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

echo "📋 Configuration:"
echo "   Limit    : ${LIMIT:-<spider default>}"
echo "   Year     : ${YEAR:-<spider default>}"
echo "   Spider   : ${SPIDER:-All}"
echo "   Docker   : $USE_DOCKER"
echo "   Clear DB : $CLEAR_DB"
echo "────────────────────────────────────────"

# -----------------------------------------------------------------------------
# Prepare directories
# -----------------------------------------------------------------------------
mkdir -p data/scraped logs

# -----------------------------------------------------------------------------
# Docker Mode
# -----------------------------------------------------------------------------
if [ "$USE_DOCKER" = true ]; then
    echo "🐳 Running via Docker..."
    export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ "$CLEAR_DB" = true ]; then
        docker compose -f docker/docker-compose.yml down -v || true
    fi
    docker compose -f docker/docker-compose.yml up --build -d
    echo "✅ Docker containers started."
    exit 0
fi

# -----------------------------------------------------------------------------
# Local Environment
# -----------------------------------------------------------------------------
if [ -f ".venv/bin/activate" ]; then
    echo "🔧 Activating virtual environment..."
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# -----------------------------------------------------------------------------
# Optional: Clear Vector DB
# -----------------------------------------------------------------------------
if [ "$CLEAR_DB" = true ]; then
    echo "🗑️  Clearing vector database..."
    python3.11 -c "from retrieval.vector_store import clear_collection; clear_collection()"
fi

# -----------------------------------------------------------------------------
# Run Scrapers
# -----------------------------------------------------------------------------
echo "🕸️  Starting scrapers..."

cd ingestion/regcrawler

PYTHON="${PYTHON:-../../.venv/bin/python3.11}"

ALL_SPIDERS=(
    "fomc"
    "fed_reserve"
    "fdic"
    "fca"
    "fincen"
    "sec_speeches"
    "sec_rules"
    "sec_enforcement"
    "cftc_enforcer"
    "basel_pdf"
    "edgar_filings"
)

# Build dynamic Scrapy argument list
SCRAPY_ARGS=()

if [ -n "$YEAR" ]; then
    SCRAPY_ARGS+=("-a" "year=$YEAR")
fi

if [ -n "$LIMIT" ]; then
    SCRAPY_ARGS+=("-a" "limit=$LIMIT")
fi

run_spider() {
    local name="$1"
    echo "🔍 Crawling: $name"

    if [ "${#SCRAPY_ARGS[@]}" -gt 0 ]; then
        PYTHONPATH="../../" "$PYTHON" -m scrapy crawl "$name" "${SCRAPY_ARGS[@]}"
    else
        PYTHONPATH="../../" "$PYTHON" -m scrapy crawl "$name"
    fi
}

# If specific spider requested
if [ -n "$SPIDER" ]; then
    if [[ ! " ${ALL_SPIDERS[*]} " =~ " ${SPIDER} " ]]; then
        echo "❌ Invalid spider: $SPIDER"
        echo "Available spiders:"
        printf "  %s\n" "${ALL_SPIDERS[@]}"
        exit 1
    fi
    run_spider "$SPIDER"
else
    for S in "${ALL_SPIDERS[@]}"; do
        run_spider "$S"
    done
fi

cd ../..

echo "✅ All spiders completed."

# -----------------------------------------------------------------------------
# Run Ingestion
# -----------------------------------------------------------------------------
echo "📥 Starting vector database ingestion..."

INGEST_ARGS=()

if [ -n "$LIMIT" ]; then
    INGEST_ARGS+=("--limit" "$LIMIT")
fi

if [ "${#INGEST_ARGS[@]}" -gt 0 ]; then
    python3.11 ingestion/ingest_scraped_docs.py "${INGEST_ARGS[@]}"
else
    python3.11 ingestion/ingest_scraped_docs.py
fi

echo ""
echo "🎉 All done!"
echo "📁 Scraped files → data/scraped/"
echo "🗄️  Vector DB     → data/chroma_db/"
echo "📜 Logs           → logs/agent.log"