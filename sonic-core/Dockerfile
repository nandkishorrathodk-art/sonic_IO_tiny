# ============================================
# SONIC Core — Production Dockerfile
# Multi-stage build compiling Native Rust Kernel (sonic-kernel-rs)
# and Python runtime
# ============================================

# Stage 1: Build Native Rust Kernel
FROM rust:1.80-slim AS rust-builder
WORKDIR /kernel-build
COPY sonic-kernel-rs/Cargo.toml sonic-kernel-rs/Cargo.lock* ./
COPY sonic-kernel-rs/src ./src
RUN cargo build --release

# Stage 2: Python builder
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY sonic-core/pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Stage 3: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nmap \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install compiled native Rust kernel binary
COPY --from=rust-builder /kernel-build/target/release/sonic-kernel /usr/local/bin/sonic-kernel
RUN chmod +x /usr/local/bin/sonic-kernel

# Create unprivileged runner user
RUN useradd -m -u 1000 sonic && chown -R sonic:sonic /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=sonic:sonic sonic-core /app

USER sonic
EXPOSE 8000

ENV APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    SONIC_KERNEL_BIN=/usr/local/bin/sonic-kernel

CMD ["uvicorn", "sonic.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
