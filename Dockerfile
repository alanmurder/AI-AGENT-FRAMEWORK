# Stage 1: Frontend builder
FROM node:20-alpine AS frontend-builder
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/index.html web/vite.config.ts web/tsconfig.json web/tsconfig.node.json ./
COPY web/src ./src
RUN npm run build

# Stage 2: Final runtime image
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set application environment variables
ENV AI_AGENT_PROJECT_ROOT=/app \
    AI_AGENT_SERVE_STATIC=true \
    AI_AGENT_STATIC_DIR=/app/web/dist \
    AI_AGENT_MEMORY_BASE_DIR=/var/lib/ai-agent-platform/workspace

# Set working directory
WORKDIR /app

# Copy the full project (web/src is excluded via .dockerignore)
COPY . .

# Install the project with sandbox extra dependencies
RUN pip install --no-cache-dir -e ".[sandbox]"

# Copy frontend build from the builder stage
COPY --from=frontend-builder /build/web/dist/ /app/web/dist/

# Create non-root user and data directories
RUN useradd --create-home --shell /bin/bash aiagent && \
    mkdir -p /var/lib/ai-agent-platform/workspace \
             /var/lib/ai-agent-platform/logs \
             /var/lib/ai-agent-platform/sessions && \
    chown -R aiagent:aiagent /var/lib/ai-agent-platform /app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER aiagent

# Expose application port
EXPOSE 8000

# Entrypoint
ENTRYPOINT ["python", "-m", "gateway.server"]
