# ============================================
# SONIC-REDA Core — Production Dockerfile
# ============================================
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nmap \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged runner user
RUN useradd -m -u 1000 sonic && chown -R sonic:sonic /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=sonic:sonic . /app

USER sonic

EXPOSE 8000

ENV APP_ENV=production \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "sonic.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
