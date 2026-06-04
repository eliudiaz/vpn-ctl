# VPN Health Monitor - Multi-stage Dockerfile
# ============================================================
# Modern container image for nodeping-like VPN monitoring

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Create wheels for all dependencies
RUN pip install --no-cache-dir wheel && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

LABEL maintainer="Affinity Infrastructure Team"
LABEL description="VPN Health Monitor - nodeping-like connectivity monitoring"
LABEL version="1.0.0"

WORKDIR /app

# Install runtime dependencies (including network diagnostic tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    traceroute \
    mtr-tiny \
    curl \
    netcat-traditional \
    dnsutils \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels
COPY --from=builder /build/requirements.txt .

# Install Python dependencies from wheels
RUN pip install --no-cache /wheels/* && \
    rm -rf /wheels

# Create non-root user (if not running as root for ICMP)
RUN useradd -m -u 1000 monitor || true

# Copy application code
COPY main.py .
COPY dashboard.html .

# Note: vpn-targets.yaml is provided by ConfigMap at runtime via volume mount

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/config || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "-u", "main.py"]
