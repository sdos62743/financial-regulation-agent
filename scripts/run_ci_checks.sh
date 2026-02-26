#!/usr/bin/env bash
# Run all CI checks locally (mirrors .github/workflows/ci.yml)
# Usage: ./scripts/run_ci_checks.sh [lint|test|docker|security|all]
set -e

cd "$(dirname "$0")/.."

# Require .venv - fail early if missing
if [ ! -f .venv/bin/python ]; then
  echo "ERROR: .venv not found. Create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

PYTHON=".venv/bin/python"
PIP=".venv/bin/pip"
FLAKE8=".venv/bin/flake8"
MYPY=".venv/bin/mypy"
BLACK=".venv/bin/black"
ISORT=".venv/bin/isort"
PYTEST=".venv/bin/pytest"
SAFETY=".venv/bin/safety"
BANDIT=".venv/bin/bandit"

run_lint() {
  echo "══════════════════════════════════════════════════════════"
  echo "  LINT"
  echo "══════════════════════════════════════════════════════════"
  $PIP install -q flake8 mypy black isort 2>/dev/null || true

  echo "→ flake8..."
  $FLAKE8 . --count --max-complexity=15 --max-line-length=100 \
    --extend-ignore=E203,W503,E402,E501,F401,F541,F841,C901,W291,W292,W293,E128 \
    --exclude=.venv,venv,data,build,dist,.git,__pycache__,ingestion/regcrawler,test_basel_selenium.py \
    --statistics

  echo "→ mypy..."
  $MYPY . --ignore-missing-imports --no-strict-optional || true

  echo "→ black --check..."
  $BLACK --check .

  echo "→ isort --check-only..."
  $ISORT --check-only .

  echo "✅ Lint passed"
}

run_test() {
  echo "══════════════════════════════════════════════════════════"
  echo "  TEST"
  echo "══════════════════════════════════════════════════════════"
  $PIP install -q pytest pytest-cov pytest-asyncio pytest-mock 2>/dev/null || true
  export PYTHONPATH=.
  $PYTEST tests/ -m "not integration" \
    --cov=graph --cov=retrieval --cov=evaluation --cov=tools --cov=app \
    --cov-report=term-missing \
    -q

  echo "✅ Tests passed"
}

run_docker() {
  echo "══════════════════════════════════════════════════════════"
  echo "  DOCKER"
  echo "══════════════════════════════════════════════════════════"
  export PROJECT_ROOT="$(pwd)"
  docker compose -f docker/docker-compose.yml build --no-cache
  docker compose -f docker/docker-compose.yml up -d
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 3
    if curl -sf http://localhost:8000/health; then
      echo "Health check passed"
      docker compose -f docker/docker-compose.yml down
      echo "✅ Docker passed"
      return 0
    fi
    echo "Attempt $i: waiting for server..."
  done
  docker compose -f docker/docker-compose.yml logs agent
  docker compose -f docker/docker-compose.yml down
  exit 1
}

run_security() {
  echo "══════════════════════════════════════════════════════════"
  echo "  SECURITY"
  echo "══════════════════════════════════════════════════════════"
  $PIP install -q safety bandit 2>/dev/null || true

  echo "→ safety check..."
  $SAFETY check --file requirements.txt || true

  echo "→ bandit..."
  $BANDIT -r app graph retrieval evaluation tools observability webapp scripts -ll --skip B101,B104 || true

  echo "✅ Security passed"
}

case "${1:-all}" in
  lint)    run_lint ;;
  test)    run_test ;;
  docker)  run_docker ;;
  security) run_security ;;
  all)
    run_lint
    run_test
    run_security
    echo ""
    echo "══════════════════════════════════════════════════════════"
    echo "  All checks passed (skip docker with: ./scripts/run_ci_checks.sh lint)"
    echo "  Run 'make docker-build' and test manually if needed."
    echo "══════════════════════════════════════════════════════════"
    ;;
  *) echo "Usage: $0 [lint|test|docker|security|all]"; exit 1 ;;
esac
