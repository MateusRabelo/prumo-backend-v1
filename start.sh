#!/bin/sh
set -e

echo "Waiting for database connection..."
python3 - << 'EOF'
import os
import sys
import time
from urllib.parse import urlparse
import psycopg

url = os.getenv("DATABASE_URL", "")
if not url:
    print("No DATABASE_URL configured, continuing...")
    sys.exit(0)

psycopg_url = url
if psycopg_url.startswith("postgres://"):
    psycopg_url = psycopg_url.replace("postgres://", "postgresql://", 1)

try:
    parsed = urlparse(psycopg_url)
    target = f"{parsed.hostname}:{parsed.port or 5432}"
except Exception:
    target = psycopg_url

print(f"Connecting to database at {target}...")

max_retries = 30
for attempt in range(1, max_retries + 1):
    try:
        conn = psycopg.connect(psycopg_url, connect_timeout=3)
        conn.close()
        print("Database is ready and accepting connections!")
        sys.exit(0)
    except Exception as e:
        print(f"Waiting for database to be ready ({attempt}/{max_retries})... ({e})")
        time.sleep(1)

print("ERROR: Database not available after 30 attempts, exiting.", file=sys.stderr)
sys.exit(1)
EOF

echo "Applying database migrations (Alembic)..."
alembic upgrade head

PORT="${PORT:-8001}"
echo "Starting FastAPI server with Uvicorn on port ${PORT} (Environment: ${ENVIRONMENT:-production})..."
if [ "$ENVIRONMENT" = "development" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
fi
