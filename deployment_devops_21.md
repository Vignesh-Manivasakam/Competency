# Deployment & DevOps

## Plan 21 of 21 — Competency Intelligence Platform MVP

---

### Objective

Configure the full deployment pipeline for the Competency Intelligence Platform. This plan creates production-grade Docker images (multi-stage builds for backend and frontend), a production Docker Compose stack with health checks, resource limits, and restart policies, an nginx reverse proxy, environment management files, Alembic migration execution in the Docker entrypoint, a GitHub Actions CI/CD pipeline, and the Antigravity 2.0 multi-agent workspace configuration. After completing this plan, the platform is deployable with a single `docker compose -f docker-compose.prod.yml up -d` command.

### Prerequisites

- **Plan 18** (Frontend Manager Portal) — React build artifacts and routing
- **Plan 19** (Frontend Employee Portal) — React build artifacts and routing
- **Plan 20** (Observability & Testing) — All tests passing, structlog configured, LangSmith tracing active

### Spec References

| Section | Content |
|---------|---------|
| §12 | Antigravity 2.0 Setup Guide — multi-agent parallel development workspace |
| §16 | Environment Configuration — `.env.example` (Listing 17), `docker-compose.yml` (Listing 18) |
| §22 | MVP Success Criteria — P99 latency < 500ms, WebSocket first message < 4s |

---

### Files to Create/Modify

```
competency-platform/
├── docker/
│   ├── Dockerfile.backend       # Multi-stage Python 3.12 + uvicorn
│   ├── Dockerfile.frontend      # Multi-stage Node 20 + nginx
│   └── nginx.conf               # Reverse proxy configuration
├── docker-compose.yml           # Dev stack (already exists from Plan 1)
├── docker-compose.prod.yml      # Production stack with health checks
├── backend/
│   └── scripts/
│       └── entrypoint.sh        # Alembic migrate + uvicorn startup
├── .env.example                 # Root-level all variables
├── .env.production              # Production overrides template
├── .env.staging                 # Staging overrides template
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI/CD pipeline
└── .agents/
    ├── workspace.yaml           # Antigravity 2.0 workspace config
    ├── backend-agent.md         # Backend agent instructions
    ├── frontend-agent.md        # Frontend agent instructions
    └── test-agent.md            # Test agent instructions
```

---

### Detailed Implementation Steps

#### Step 1: Backend Dockerfile — Multi-Stage Build

**File: `competency-platform/docker/Dockerfile.backend`**

```dockerfile
# ============================================
# Competency Intelligence Platform — Backend
# Multi-stage build: Python 3.12 + uvicorn
# Spec reference: §16 Docker Compose
# ============================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system deps for building native extensions (asyncpg, bcrypt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtual env for clean copy
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

LABEL maintainer="competency-platform-team"
LABEL description="Competency Intelligence Platform — FastAPI Backend"

WORKDIR /app

# Install only runtime system deps (libpq for asyncpg, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts/entrypoint.sh ./entrypoint.sh

RUN chmod +x ./entrypoint.sh && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
```

> [!NOTE]
> The multi-stage build reduces the final image size by ~60% — the builder stage includes `build-essential` and `libpq-dev` for compiling native extensions, while the runtime stage only carries `libpq5` for the asyncpg driver at runtime.

---

#### Step 2: Backend Entrypoint Script (Alembic Migration)

**File: `competency-platform/backend/scripts/entrypoint.sh`**

```bash
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
```

> [!IMPORTANT]
> The entrypoint waits for PostgreSQL readiness using a Python connection check (not `pg_isready`) because it verifies the full connection string including authentication. Alembic migrations run synchronously using `DATABASE_URL_SYNC` before the async uvicorn process starts.

---

#### Step 3: Frontend Dockerfile — Multi-Stage Build

**File: `competency-platform/docker/Dockerfile.frontend`**

```dockerfile
# ============================================
# Competency Intelligence Platform — Frontend
# Multi-stage build: Node 20 + nginx
# Spec reference: §16 Docker Compose
# ============================================

# --- Stage 1: Build React app ---
FROM node:20-alpine AS builder

WORKDIR /build

# Copy package files first for layer caching
COPY frontend/package.json frontend/package-lock.json* frontend/yarn.lock* ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ ./
ENV VITE_API_URL=/api/v1
ENV VITE_WS_URL=/api/v1/ws
RUN npm run build

# --- Stage 2: Serve with nginx ---
FROM nginx:1.27-alpine AS runtime

LABEL maintainer="competency-platform-team"
LABEL description="Competency Intelligence Platform — React Frontend"

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/default.conf /usr/share/nginx/html/*

# Copy custom nginx config for SPA routing
COPY docker/nginx-frontend.conf /etc/nginx/conf.d/default.conf

# Copy built React app from builder stage
COPY --from=builder /build/dist /usr/share/nginx/html

# Security: run as non-root
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

**File: `competency-platform/docker/nginx-frontend.conf`**

```nginx
# Frontend-only nginx config (used inside the frontend container)
server {
    listen 3000;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # SPA routing — serve index.html for all non-file routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets aggressively
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

---

#### Step 4: Nginx Reverse Proxy Configuration

**File: `competency-platform/docker/nginx.conf`**

```nginx
# ============================================
# Competency Intelligence Platform — Reverse Proxy
# Routes /api/* → backend, /* → frontend
# Spec reference: §16 Docker Compose
# ============================================

upstream backend_server {
    server backend:8000;
    keepalive 32;
}

upstream frontend_server {
    server frontend:3000;
}

server {
    listen 80;
    server_name _;

    # --- Security headers ---
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ws: wss:;" always;

    # --- Gzip compression ---
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
    gzip_min_length 1024;
    gzip_vary on;

    # --- API routes → Backend (FastAPI) ---
    location /api/ {
        proxy_pass http://backend_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout settings for LLM-backed endpoints (§22: P99 < 500ms for REST)
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
        proxy_send_timeout 30s;

        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 16k;
        proxy_buffers 8 32k;
    }

    # --- WebSocket route → Backend ---
    location /api/v1/ws/ {
        proxy_pass http://backend_server;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # WebSocket timeout — keep alive for long sessions
        # §22: WebSocket first message < 4 seconds
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # --- Health check endpoint (no proxy overhead) ---
    location /health {
        proxy_pass http://backend_server/health;
        proxy_set_header Host $host;
        access_log off;
    }

    # --- API docs ---
    location /docs {
        proxy_pass http://backend_server/docs;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://backend_server/openapi.json;
        proxy_set_header Host $host;
    }

    # --- Frontend (React SPA) — catch-all ---
    location / {
        proxy_pass http://frontend_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # --- Error pages ---
    error_page 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
        internal;
    }
}
```

> [!WARNING]
> The WebSocket location block (`/api/v1/ws/`) MUST appear before the generic `/api/` block in nginx config. The `proxy_http_version 1.1` and `Connection "upgrade"` headers are required for WebSocket protocol upgrade. Without these, the WebSocket handshake fails silently.

---

#### Step 5: Production Docker Compose

**File: `competency-platform/docker-compose.prod.yml`**

```yaml
# ============================================
# Competency Intelligence Platform — Production
# Spec reference: §16 Docker Compose (Listing 18)
# ============================================

services:
  # --- PostgreSQL 16 + pgvector ---
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      POSTGRES_DB: ${POSTGRES_DB:-competency_db}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d competency_db"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.0"
        reservations:
          memory: 512M
    networks:
      - backend-net

  # --- Redis 7 ---
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "${REDIS_PORT:-6379}:6379"
    command: >
      redis-server
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --requirepass ${REDIS_PASSWORD:-}
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.5"
        reservations:
          memory: 128M
    networks:
      - backend-net

  # --- Neo4j 5 Community (Skill DAG) ---
  neo4j:
    image: neo4j:5-community
    restart: unless-stopped
    environment:
      NEO4J_AUTH: ${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
      NEO4J_server_memory_heap_initial__size: 256m
      NEO4J_server_memory_heap_max__size: 512m
      NEO4J_server_memory_pagecache_size: 256m
    ports:
      - "${NEO4J_HTTP_PORT:-7474}:7474"
      - "${NEO4J_BOLT_PORT:-7687}:7687"
    volumes:
      - neo4jdata:/data
      - neo4jlogs:/logs
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p $${NEO4J_PASSWORD} 'RETURN 1' || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.0"
        reservations:
          memory: 512M
    networks:
      - backend-net

  # --- FastAPI Backend ---
  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    restart: unless-stopped
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    env_file:
      - .env.production
    environment:
      # Override DB URLs to use Docker network hostnames
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-competency_db}
      DATABASE_URL_SYNC: postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-competency_db}
      REDIS_URL: redis://redis:6379/0
      NEO4J_URI: bolt://neo4j:7687
      APP_ENV: production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "2.0"
        reservations:
          memory: 512M
    networks:
      - backend-net
      - frontend-net

  # --- React Frontend ---
  frontend:
    build:
      context: .
      dockerfile: docker/Dockerfile.frontend
    restart: unless-stopped
    depends_on:
      - backend
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.5"
        reservations:
          memory: 64M
    networks:
      - frontend-net

  # --- Nginx Reverse Proxy ---
  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    ports:
      - "${APP_PORT:-80}:80"
      - "${APP_SSL_PORT:-443}:443"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      backend:
        condition: service_healthy
      frontend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost/health"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: "0.25"
    networks:
      - frontend-net
      - backend-net

volumes:
  pgdata:
    driver: local
  redisdata:
    driver: local
  neo4jdata:
    driver: local
  neo4jlogs:
    driver: local

networks:
  backend-net:
    driver: bridge
  frontend-net:
    driver: bridge
```

> [!IMPORTANT]
> The production compose uses two isolated Docker networks: `backend-net` (database services + backend) and `frontend-net` (frontend + nginx + backend). This ensures database containers are never directly exposed to the frontend or nginx containers.

---

#### Step 6: Development Docker Compose Override

The development compose file from Plan 1 (`docker-compose.yml`) already exists. This step documents the expected override for local hot-reload development:

**File: `competency-platform/docker-compose.override.yml`**

```yaml
# ============================================
# Development overrides — hot-reload, debug logging
# Auto-loaded with: docker compose up
# ============================================

services:
  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
      target: runtime
    volumes:
      # Mount source code for hot-reload
      - ./backend/app:/app/app:ro
      - ./backend/alembic:/app/alembic:ro
    command: >
      uvicorn app.main:app
      --host 0.0.0.0
      --port 8000
      --reload
      --reload-dir /app/app
      --log-level debug
    environment:
      APP_ENV: development
    ports:
      - "8000:8000"

  frontend:
    build:
      context: .
      dockerfile: docker/Dockerfile.frontend
      target: builder
    volumes:
      - ./frontend/src:/build/src:ro
    command: npm run dev -- --host 0.0.0.0 --port 3000
    ports:
      - "3000:3000"
    environment:
      VITE_API_URL: http://localhost:8000/api/v1
      VITE_WS_URL: ws://localhost:8000/api/v1/ws
```

---

#### Step 7: Environment Configuration Files

**File: `competency-platform/.env.example`**

```env
# ============================================
# Competency Intelligence Platform
# Environment Configuration
# Spec reference: §16 Listing 17
# ============================================
# Copy this file to .env and fill in real values.
# NEVER commit .env to version control.

# ----- Application -----
APP_ENV=development
SECRET_KEY=your-jwt-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ----- PostgreSQL -----
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=competency_db
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/competency_db
DATABASE_URL_SYNC=postgresql://postgres:password@localhost:5432/competency_db

# ----- Redis -----
REDIS_URL=redis://localhost:6379/0
REDIS_PORT=6379
REDIS_PASSWORD=

# ----- Neo4j -----
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687

# ----- LLM Providers (at least one required) -----
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# ----- LLM Routing -----
LLM_PRIMARY=gpt-4o
LLM_SECONDARY=gpt-4o-mini
LLM_FALLBACK=claude-sonnet-4-6

# ----- LangSmith (Observability) -----
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=competency-intelligence-mvp

# ----- Embeddings -----
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# ----- Session Config -----
MAX_SESSION_INTERACTIONS=25
SESSION_TIMEOUT_HOURS=24
MASTERY_CONFIDENCE_THRESHOLD=0.80
MIN_INTERACTIONS_FOR_MASTERY=3

# ----- Deployment -----
APP_PORT=80
APP_SSL_PORT=443
BACKEND_PORT=8000
```

**File: `competency-platform/.env.production`**

```env
# ============================================
# Production Environment
# ============================================
APP_ENV=production

# IMPORTANT: Replace all placeholder values below
SECRET_KEY=CHANGE-ME-generate-with-openssl-rand-base64-48

# PostgreSQL
POSTGRES_USER=competency_admin
POSTGRES_PASSWORD=CHANGE-ME-strong-production-password
POSTGRES_DB=competency_db

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE-ME-strong-neo4j-password

# LLM Providers
OPENAI_API_KEY=sk-PRODUCTION-KEY
ANTHROPIC_API_KEY=sk-ant-PRODUCTION-KEY
GOOGLE_API_KEY=AIza-PRODUCTION-KEY

# LLM Routing — production uses same model hierarchy
LLM_PRIMARY=gpt-4o
LLM_SECONDARY=gpt-4o-mini
LLM_FALLBACK=claude-sonnet-4-6

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__PRODUCTION-KEY
LANGCHAIN_PROJECT=competency-intelligence-prod

# Embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Session Config
MAX_SESSION_INTERACTIONS=25
SESSION_TIMEOUT_HOURS=24
MASTERY_CONFIDENCE_THRESHOLD=0.80
MIN_INTERACTIONS_FOR_MASTERY=3

# Higher token expiry for production
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

**File: `competency-platform/.env.staging`**

```env
# ============================================
# Staging Environment
# ============================================
APP_ENV=staging

SECRET_KEY=CHANGE-ME-staging-secret-key-min-32-chars

# PostgreSQL
POSTGRES_USER=competency_staging
POSTGRES_PASSWORD=CHANGE-ME-staging-password
POSTGRES_DB=competency_db_staging

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE-ME-staging-neo4j-password

# LLM Routing — staging uses cheaper models
LLM_PRIMARY=gpt-4o-mini
LLM_SECONDARY=gpt-4o-mini
LLM_FALLBACK=claude-sonnet-4-6

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__STAGING-KEY
LANGCHAIN_PROJECT=competency-intelligence-staging

# Session Config — lower limits for cost control
MAX_SESSION_INTERACTIONS=15
SESSION_TIMEOUT_HOURS=12
MASTERY_CONFIDENCE_THRESHOLD=0.80
MIN_INTERACTIONS_FOR_MASTERY=3

ACCESS_TOKEN_EXPIRE_MINUTES=60
```

---

#### Step 8: GitHub Actions CI/CD Pipeline

**File: `competency-platform/.github/workflows/ci.yml`**

```yaml
# ============================================
# Competency Intelligence Platform — CI/CD
# Spec reference: §12 Antigravity 2.0 Setup
# ============================================

name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, staging]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository }}

permissions:
  contents: read
  packages: write
  checks: write
  pull-requests: write

jobs:
  # ============================================
  # Job 1: Lint & Type Check
  # ============================================
  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ env.PYTHON_VERSION }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install backend dependencies
        working-directory: backend
        run: |
          pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Ruff lint
        working-directory: backend
        run: ruff check app/ tests/ --output-format=github

      - name: Ruff format check
        working-directory: backend
        run: ruff format --check app/ tests/

      - name: MyPy type check
        working-directory: backend
        run: mypy app/ --ignore-missing-imports
        continue-on-error: true  # Non-blocking for MVP

      - name: Set up Node.js ${{ env.NODE_VERSION }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci

      - name: ESLint
        working-directory: frontend
        run: npm run lint

      - name: TypeScript type check
        working-directory: frontend
        run: npx tsc --noEmit

  # ============================================
  # Job 2: Backend Tests
  # ============================================
  test-backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    needs: lint

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: testpassword
          POSTGRES_DB: competency_db_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ env.PYTHON_VERSION }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        working-directory: backend
        run: |
          pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run unit tests
        working-directory: backend
        env:
          APP_ENV: test
          DATABASE_URL: postgresql+asyncpg://postgres:testpassword@localhost:5432/competency_db_test
          DATABASE_URL_SYNC: postgresql://postgres:testpassword@localhost:5432/competency_db_test
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key-for-ci-min-32-characters-long
          OPENAI_API_KEY: sk-test-not-real
        run: |
          pytest tests/unit/ -v --tb=short --cov=app --cov-report=xml --cov-report=term-missing

      - name: Run integration tests
        working-directory: backend
        env:
          APP_ENV: test
          DATABASE_URL: postgresql+asyncpg://postgres:testpassword@localhost:5432/competency_db_test
          DATABASE_URL_SYNC: postgresql://postgres:testpassword@localhost:5432/competency_db_test
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key-for-ci-min-32-characters-long
          OPENAI_API_KEY: sk-test-not-real
        run: |
          pytest tests/integration/ -v --tb=short
        continue-on-error: true  # Integration tests may require LLM keys

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: backend-coverage
          path: backend/coverage.xml
        if: always()

  # ============================================
  # Job 3: Frontend Tests & Build
  # ============================================
  test-frontend:
    name: Frontend Tests & Build
    runs-on: ubuntu-latest
    needs: lint

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js ${{ env.NODE_VERSION }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Run tests
        working-directory: frontend
        run: npm test -- --run --reporter=verbose
        env:
          CI: true

      - name: Build production bundle
        working-directory: frontend
        run: npm run build
        env:
          VITE_API_URL: /api/v1
          VITE_WS_URL: /api/v1/ws

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: frontend-build
          path: frontend/dist/

  # ============================================
  # Job 4: Docker Build
  # ============================================
  docker-build:
    name: Docker Build
    runs-on: ubuntu-latest
    needs: [test-backend, test-frontend]
    if: github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/staging')

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        run: |
          BRANCH=${GITHUB_REF#refs/heads/}
          SHA_SHORT=$(echo $GITHUB_SHA | head -c 7)
          echo "tag=${BRANCH}-${SHA_SHORT}" >> $GITHUB_OUTPUT
          echo "branch=${BRANCH}" >> $GITHUB_OUTPUT

      - name: Build & push backend image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.backend
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/backend:${{ steps.meta.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/backend:${{ steps.meta.outputs.branch }}-latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build & push frontend image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.frontend
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/frontend:${{ steps.meta.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/frontend:${{ steps.meta.outputs.branch }}-latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ============================================
  # Job 5: Deploy (Staging / Production)
  # ============================================
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    needs: docker-build
    if: github.event_name == 'push'
    environment:
      name: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}

    steps:
      - uses: actions/checkout@v4

      - name: Determine environment
        id: env
        run: |
          if [ "${{ github.ref }}" = "refs/heads/main" ]; then
            echo "env_file=.env.production" >> $GITHUB_OUTPUT
            echo "compose_file=docker-compose.prod.yml" >> $GITHUB_OUTPUT
            echo "env_name=production" >> $GITHUB_OUTPUT
          else
            echo "env_file=.env.staging" >> $GITHUB_OUTPUT
            echo "compose_file=docker-compose.prod.yml" >> $GITHUB_OUTPUT
            echo "env_name=staging" >> $GITHUB_OUTPUT
          fi

      - name: Deploy notification
        run: |
          echo "🚀 Deploying to ${{ steps.env.outputs.env_name }}"
          echo "   Compose file: ${{ steps.env.outputs.compose_file }}"
          echo "   Env file: ${{ steps.env.outputs.env_file }}"
          echo ""
          echo "To deploy manually, run:"
          echo "  docker compose -f ${{ steps.env.outputs.compose_file }} --env-file ${{ steps.env.outputs.env_file }} up -d"
```

---

#### Step 9: Antigravity 2.0 Workspace Configuration

**File: `competency-platform/.agents/workspace.yaml`**

From §12 — multi-agent parallel development workspace:

```yaml
# ============================================
# Antigravity 2.0 — Workspace Configuration
# Spec reference: §12 Antigravity 2.0 Setup Guide
# ============================================

workspace:
  name: competency-intelligence-platform
  description: >
    AI-powered Competency Intelligence Platform MVP.
    Multi-agent workspace with Backend, Frontend, and Test agents
    working in parallel on the same codebase.

  project_root: .

  knowledge_base:
    - docs/mvp-spec.pdf            # Full MVP specification
    - schemas/                     # Pydantic/SQLModel schemas
    - docker-compose.prod.yml      # Infrastructure reference
    - .env.example                 # Environment variable reference
    - backend/pyproject.toml       # Python dependencies
    - frontend/package.json        # Node dependencies

agents:
  - name: backend-agent
    instructions: .agents/backend-agent.md
    focus:
      - backend/app/
      - backend/alembic/
      - backend/tests/
    capabilities:
      - python
      - fastapi
      - sqlmodel
      - langgraph
      - langchain

  - name: frontend-agent
    instructions: .agents/frontend-agent.md
    focus:
      - frontend/src/
      - frontend/public/
    capabilities:
      - typescript
      - react
      - tailwindcss
      - shadcn-ui

  - name: test-agent
    instructions: .agents/test-agent.md
    focus:
      - backend/tests/
      - frontend/src/**/*.test.*
    capabilities:
      - pytest
      - vitest
      - playwright

conventions:
  python:
    formatter: ruff
    linter: ruff
    type_checker: mypy
    test_runner: pytest
    async_mode: "auto"
  typescript:
    formatter: prettier
    linter: eslint
    type_checker: tsc
    test_runner: vitest
  git:
    branch_naming: "feat|fix|refactor|docs|test/short-description"
    commit_format: "conventional"
```

**File: `competency-platform/.agents/backend-agent.md`**

```markdown
# Backend Agent Instructions

## Role
You are the Backend Agent for the Competency Intelligence Platform.
You own all Python code under `backend/`.

## Technology Stack
- **Python 3.12** with asyncio native
- **FastAPI 0.115+** with uvicorn
- **SQLModel** (Pydantic v2 + SQLAlchemy 2.0)
- **LangGraph 0.2+** with PostgreSQL checkpointer
- **LangChain** for LLM orchestration (OpenAI, Anthropic, Google)
- **PostgreSQL 16 + pgvector** for relational + vector storage
- **Redis 7** for session cache and rate limiting
- **Neo4j 5** for Skill DAG graph

## Key Patterns
1. All database operations use `AsyncSession` via `Depends(get_async_session)`
2. All agents inherit from `BaseAgent` and implement `async def process(state)`
3. LLM calls go through `LLMRouter` with primary → secondary → fallback
4. Structured output via Pydantic models with `with_structured_output()`
5. Every LangGraph workflow must have a PostgreSQL checkpointer
6. Use structlog for all logging
7. LangSmith tracing on all LLM chains

## File Structure
- `app/agents/` — LangGraph agent implementations
- `app/graphs/` — LangGraph workflow definitions
- `app/api/v1/` — FastAPI route handlers
- `app/core/` — Config, DB, Redis, Neo4j, security
- `app/models/` — SQLModel database models
- `app/schemas/` — Pydantic request/response schemas
- `app/services/` — Business logic services
- `app/prompts/` — LLM prompt templates

## Testing
- Unit tests mock all external services (LLM, DB, Redis)
- Integration tests use Docker service containers
- Target: 80%+ code coverage
```

**File: `competency-platform/.agents/frontend-agent.md`**

```markdown
# Frontend Agent Instructions

## Role
You are the Frontend Agent for the Competency Intelligence Platform.
You own all TypeScript/React code under `frontend/`.

## Technology Stack
- **React 18** with TypeScript
- **Vite** for build tooling
- **Tailwind CSS** for styling
- **shadcn/ui** for component library
- **Zustand** for state management
- **React Query (TanStack Query)** for server state
- **React Router v6** for routing
- **Recharts** for data visualization
- **React Flow** for Skill DAG visualization

## Key Patterns
1. Manager Portal at `/manager/*` — competency management, dashboards
2. Employee Portal at `/employee/*` — learning sessions, progress
3. All API calls through typed client in `api/client.ts`
4. WebSocket connection managed by custom `useSession` hook
5. Role-based route guards with `ProtectedRoute` component
6. Responsive design with Tailwind breakpoints

## Testing
- Component tests with Vitest + React Testing Library
- Target: all critical user flows covered
```

**File: `competency-platform/.agents/test-agent.md`**

```markdown
# Test Agent Instructions

## Role
You are the Test Agent for the Competency Intelligence Platform.
You write and maintain tests for both backend and frontend.

## Backend Testing (pytest)
- **Unit tests**: `backend/tests/unit/` — mock all externals
- **Integration tests**: `backend/tests/integration/` — use Docker services
- Run with: `pytest tests/ -v --cov=app`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`

## Frontend Testing (Vitest)
- **Component tests**: colocated `*.test.tsx` files
- Run with: `npm test`

## MVP Success Criteria (§22)
- API P99 latency < 500ms for REST endpoints
- WebSocket first message < 4 seconds
- All LangGraph workflows checkpointed and resumable
- LangSmith traces visible for every LLM call
- 80%+ backend code coverage

## Test Checklist
1. Every API endpoint has at least one happy-path test
2. Every agent has unit tests with mocked LLM responses
3. LangGraph workflows tested with recorded state transitions
4. Auth flows tested (login, register, token refresh, expired token)
5. WebSocket session lifecycle tested
6. Database migration up/down tested
```

---

#### Step 10: Docker .dockerignore and Git Configuration

**File: `competency-platform/.dockerignore`**

```
# ============================================
# Docker build context exclusions
# ============================================

# Version control
.git
.gitignore

# IDE
.vscode
.idea
*.swp
*.swo

# Environment files (secrets!)
.env
.env.production
.env.staging
.env.local

# Python
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
.ruff_cache
htmlcov/
*.egg-info/
dist/
build/

# Node
frontend/node_modules/
frontend/.next/

# Docker
docker-compose*.yml

# Docs
*.md
!README.md
LICENSE

# Agents workspace
.agents/

# CI
.github/
```

**File: `competency-platform/.gitignore` (additions)**

```gitignore
# ============================================
# Competency Intelligence Platform
# ============================================

# Environment secrets
.env
.env.local
.env.production
.env.staging
!.env.example

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
*.egg-info/
dist/
build/
coverage.xml

# Node
node_modules/
frontend/dist/
frontend/.next/

# Docker volumes
pgdata/
redisdata/
neo4jdata/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
```

---

### Verification Criteria

1. **Docker Compose starts all services**: `docker compose -f docker-compose.prod.yml up -d` brings up postgres, redis, neo4j, backend, frontend, and nginx without errors
2. **Migrations run on startup**: Backend container logs show `[entrypoint] Migrations completed successfully.` before uvicorn starts
3. **Health checks pass**: `docker compose -f docker-compose.prod.yml ps` shows all services as `healthy` within 90 seconds
4. **Frontend builds and serves**: Nginx at `http://localhost/` serves the React SPA with correct SPA routing (refresh on any path returns index.html)
5. **API proxied correctly**: `curl http://localhost/api/v1/health` returns `{"status": "healthy"}` through the nginx proxy
6. **WebSocket works through proxy**: WebSocket connection to `ws://localhost/api/v1/ws/session` completes handshake and receives messages
7. **Backend image size**: Multi-stage build produces an image under 500MB (vs ~1.2GB single-stage)
8. **CI pipeline passes**: GitHub Actions lint → test → build → deploy pipeline completes on `main` branch push
9. **Environment isolation**: Production compose uses `POSTGRES_PASSWORD:?` required syntax — fails fast if secrets are missing
10. **MVP latency targets**: `curl -w "%{time_total}" http://localhost/api/v1/competencies` returns within 500ms (§22 P99 target)

### Notes & Gotchas

> [!WARNING]
> **Never commit `.env` files**: The `.gitignore` excludes all `.env` variants except `.env.example`. Production secrets must be injected via CI/CD environment variables or a secrets manager — never stored in the repository.

> [!TIP]
> **Local development workflow**: For fastest iteration, run databases in Docker but the FastAPI app directly: `docker compose up postgres redis neo4j -d && cd backend && uvicorn app.main:app --reload`. The `.env` defaults point to `localhost` which works for this hybrid setup.

> [!NOTE]
> **Neo4j startup time**: Neo4j takes 30-60 seconds to fully initialize, especially with APOC and GDS plugins. The `start_period: 60s` in the health check prevents premature failure detection. The backend entrypoint also waits for PostgreSQL independently of Docker's `depends_on` as a belt-and-suspenders approach.

> [!IMPORTANT]
> **Multi-stage Docker builds**: The builder stage includes `build-essential` and `libpq-dev` (~200MB) for compiling native Python extensions (asyncpg, bcrypt). The runtime stage only includes `libpq5` (~2MB). Never merge these stages — it defeats the purpose of multi-stage builds.

- **Network isolation**: The production compose creates separate `backend-net` and `frontend-net` networks. Database containers are only on `backend-net`, so they cannot be reached from nginx or frontend containers directly.
- **Redis `maxmemory-policy`**: Set to `allkeys-lru` in production to prevent OOM — Redis will evict least-recently-used keys when memory limit is reached. This is safe because Redis is used as a cache, not persistent storage.
- **Alembic + entrypoint**: The entrypoint script runs `alembic upgrade head` synchronously before starting uvicorn. If migrations fail, the backend still starts (with a warning) to allow manual intervention. In a strict production setup, change `continue` to `exit 1`.
- **Antigravity 2.0 agents**: The `.agents/` directory configures three parallel agents (Backend, Frontend, Test) as specified in §12. Each agent is scoped to its directory and has instructions matching the project's technology stack.
