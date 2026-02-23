#!/bin/bash
# =============================================================================
# run_all.sh - Master Production Runner for Financial Regulation Agent
# =============================================================================

set -e  # Exit immediately if any command fails

echo "🚀 Financial Regulation Agent - Master Runner"

# Default values
LIMIT="all"
YEAR="All"
USE_DOCKER=false
CLEAR_DB=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --year)
            YEAR="$2"
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
            echo "Usage: ./run_all.sh [--limit N] [--year YEAR] [--docker] [--clear]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

echo "📋 Configuration:"
echo "   Limit    : $LIMIT"
echo "   Year     : $YEAR"
echo "   Docker   : $USE_DOCKER"
echo "   Clear DB : $CLEAR_DB"
echo "────────────────────────────────────────"

# Create necessary directories
mkdir -p data/scraped data/basel_pdfs logs

# =============================================
# Initialize Environment
# =============================================
if [ "$USE_DOCKER" = true ]; then
    echo "🐳 Running via Docker..."
    if [ "$CLEAR_DB" = true ]; then
        docker compose -f docker/docker-compose.yml down -v || true
    fi
    docker compose -f docker/docker-compose.yml up --build -d
    echo "✅ Docker containers started."
    exit 0
fi

# Local Mode
if [ -f ".venv/bin/activate" ]; then
    echo "🔧 Activating virtual environment..."
    source .venv/bin/activate
fi

# Optional: Clear database using the singleton we fixed
if [ "$CLEAR_DB" = true ]; then
    echo "🗑️  Clearing vector database..."
    python3.11 -c "from retrieval.vector_store import clear_collection; clear_collection()"
fi

# =============================================
# Run Scrapers
# =============================================
echo "🕸️  Starting scrapers..."

# Move to the Scrapy project directory
cd ingestion/regcrawler
PYTHON="${PYTHON:-../../.venv/bin/python3.11}"

# List of spiders: must match spider "name" in regcrawler/regcrawler/spiders/*.py
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

# Validate --spider if provided
if [ -n "$SPIDER" ]; then
    valid=false
    for S in "${ALL_SPIDERS[@]}"; do
        if [ "$SPIDER" = "$S" ]; then valid=true; break; fi
    done
    if [ "$valid" = false ]; then
        echo "❌ Unknown spider: ${SPIDER_STYLE}${SPIDER}${RESET}"
        echo "   Available:"
        for s in "${ALL_SPIDERS[@]}"; do echo "     ${SPIDER_STYLE}${s}${RESET}"; done
        exit_code=1; exit $exit_code
    fi
    echo "🔍 Crawling: ${SPIDER_STYLE}${SPIDER}${RESET}..."
    PYTHONPATH="../../" "$PYTHON" -m scrapy crawl "$SPIDER" -a year="$YEAR" -a limit="$LIMIT"
else
    for S in "${ALL_SPIDERS[@]}"; do
        echo "🔍 Crawling: ${SPIDER_STYLE}${S}${RESET}..."
        PYTHONPATH="../../" "$PYTHON" -m scrapy crawl "$S" -a year="$YEAR" -a limit="$LIMIT"
    done
fi

# Return to project root
cd ../..

echo "✅ All spiders completed."

# =============================================
# Run Ingestion
# =============================================
echo "📥 Starting vector database ingestion..."

# Use our Python 3.11 environment to run the ingestion script
python3.11 ingestion/ingest_scraped_docs.py --limit "$LIMIT"

echo ""
echo "🎉 All done!"
echo "📁 Scraped files → data/scraped/"
echo "🗄️  Vector DB     → data/chroma_db/"
echo "📜 Logs          → logs/agent.log"