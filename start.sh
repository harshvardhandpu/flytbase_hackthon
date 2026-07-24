#!/usr/bin/env bash
# ── ScoutOS — Production Entrypoint ──────────────────────────────────
# Runs database migrations, then starts the FastAPI application.
# Designed for Railway / Docker deployments.
#
# Environment variables:
#   PORT           — HTTP port (default: 8000)
#   DATABASE_URL   — PostgreSQL connection string
#   APP_ENV        — Environment name (default: production)
# ──────────────────────────────────────────────────────────────────────
set -e

PORT="${PORT:-8000}"
APP_ENV="${APP_ENV:-production}"

echo "=== ScoutOS Starting ==="
echo "Environment: ${APP_ENV}"
echo "Port: ${PORT}"

# ── Database Migrations ─────────────────────────────────────────────
echo ""
echo "--- Running database migrations ---"
alembic upgrade head
echo "Migrations complete."

# ── Demo Data (first-run only) ──────────────────────────────────────
echo ""
echo "--- Seeding demo data ---"
python scripts/seed_demo_data.py 2>&1 || echo "Seed script skipped or failed (non-fatal)"
echo "Seed complete."

# ── Start Server ────────────────────────────────────────────────────
echo ""
echo "--- Starting uvicorn on 0.0.0.0:${PORT} ---"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --log-level info
