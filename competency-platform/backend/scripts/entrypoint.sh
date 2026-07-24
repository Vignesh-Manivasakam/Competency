#!/bin/bash
set -e

# ============================================
# Competency Intelligence Platform — Entrypoint
# Runs Alembic migrations before starting uvicorn
# Spec reference: §16 Docker Compose, §2.2 Alembic
# ============================================

echo "========================================="
echo " Competency Intelligence Platform"
echo " Environment: ${APP_ENV:-development}"
echo "========================================="

# --- Wait for PostgreSQL to be ready ---
echo "[entrypoint] Waiting for PostgreSQL..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if python -c "
import sys
try:
    import psycopg
    conn = psycopg.connect('${DATABASE_URL_SYNC}')
    conn.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "[entrypoint] PostgreSQL is ready."
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "[entrypoint] PostgreSQL not ready (attempt $RETRY_COUNT/$MAX_RETRIES)..."
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "[entrypoint] ERROR: PostgreSQL not available after $MAX_RETRIES attempts."
    exit 1
fi

# --- Run Alembic migrations ---
echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "[entrypoint] Migrations completed successfully."
else
    echo "[entrypoint] WARNING: Migrations failed. Continuing with existing schema."
fi

# --- Enable pgvector extension (idempotent) ---
echo "[entrypoint] Ensuring pgvector extension..."
python -c "
import psycopg
conn = psycopg.connect('${DATABASE_URL_SYNC}')
conn.autocommit = True
conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
conn.close()
print('[entrypoint] pgvector extension ready.')
"

# --- Execute the main command (uvicorn) ---
echo "[entrypoint] Starting application server..."
exec "$@"
