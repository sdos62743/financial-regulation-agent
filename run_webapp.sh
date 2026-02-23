#!/bin/bash
# =============================================================================
# run_webapp.sh - Full Feature Production Web Server Startup Script
# Optimized for macOS (Bash 3.2+) and Linux
# =============================================================================
# Usage:
#    ./run_webapp.sh             → Production mode (Gunicorn + Uvicorn)
#    ./run_webapp.sh --dev       → Development mode (Uvicorn + Auto-reload)
#    ./run_webapp.sh --port 8080 → Custom port
# =============================================================================

set -e  # Exit immediately if any command fails

echo "🚀 Financial Regulation Agent - Web Server"

# ====================== 1. Configuration ======================
MODE="production"
HOST="0.0.0.0"
PORT=8000
WORKERS=2          # Recommended: 2 × (CPU cores) - 1 for production
LOG_LEVEL="info"
APP_MODULE="webapp.server:app"

# Absolute path of the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ====================== 2. Argument Parsing ======================
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            MODE="development"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./run_webapp.sh [--dev] [--port PORT] [--workers N]"
            echo ""
            echo "Options:"
            echo "  --dev         Start in dev mode with auto-reload"
            echo "  --port        Specify port (default: 8000)"
            echo "  --workers     Number of worker processes (Prod only)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# ====================== 3. Virtual Environment ======================
if [ -d "$PROJECT_ROOT/.venv" ]; then
    echo "🔧 Activating virtual environment (.venv)..."
    source "$PROJECT_ROOT/.venv/bin/activate"
elif [ -d "$PROJECT_ROOT/venv" ]; then
    echo "🔧 Activating virtual environment (venv)..."
    source "$PROJECT_ROOT/venv/bin/activate"
else
    echo "❌ Error: Virtual environment (.venv or venv) not found!"
    echo "   Please create one: python -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# ====================== 4. Environment Setup ======================
# Add project root to PYTHONPATH so it finds 'webapp', 'retrieval', etc.
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Change to project root to ensure relative imports work inside Python
cd "$PROJECT_ROOT"

# Universal Uppercase conversion (fixes macOS 'bad substitution' error)
MODE_UPPER=$(echo "$MODE" | tr '[:lower:]' '[:upper:]')

echo "🌐 Starting server in $MODE_UPPER mode"
echo "   URL      : http://$HOST:$PORT"
echo "   Root     : $PROJECT_ROOT"
echo "   Workers  : $( [ "$MODE" = "production" ] && echo "$WORKERS" || echo "1 (reload mode)" )"
echo "────────────────────────────────────────────────────────────────"

# ====================== 5. Launch Server ======================
if [ "$MODE" = "development" ]; then
    echo "🔄 Development mode with auto-reload enabled"
    # Direct Uvicorn call for development features
    exec uvicorn "$APP_MODULE" \
        --host "$HOST" \
        --port "$PORT" \
        --reload \
        --log-level debug

else
    echo "⚡ Production mode (Gunicorn + Uvicorn workers)"
    
    # Check if gunicorn is installed
    if ! python3.11 -c "import gunicorn" &> /dev/null; then
        echo "⚠️  gunicorn not found. Installing..."
        pip install gunicorn
    fi

    # The --chdir flag is the critical fix for ModuleNotFoundError
    # It forces the worker processes to start in the project root.
    exec gunicorn "$APP_MODULE" \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind "$HOST:$PORT" \
        --chdir "$PROJECT_ROOT" \
        --timeout 120 \
        --keep-alive 5 \
        --log-level "$LOG_LEVEL" \
        --access-logfile - \
        --error-logfile -
fi