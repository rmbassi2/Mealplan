# Multi-stage Dockerfile for Dinner Decider
# Stage 1: Build virtual environment and install dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Final lightweight runtime container
FROM python:3.12-slim AS final

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Create a non-privileged user and group for security
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/false appuser

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application files
COPY app/ ./app/
COPY static/ ./static/
COPY main.py .

# Ensure data directory exists and app files are owned by appuser
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

# Declare persistent data volume
VOLUME ["/app/data"]

# Switch to non-root user
USER appuser

EXPOSE 8000

# Healthcheck testing the /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + str(__import__('os').getenv('PORT', 8000)) + '/health')" || exit 1

CMD ["python", "main.py"]
