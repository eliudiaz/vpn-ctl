# VPN Health App - Lightweight monitoring container
FROM python:3.11-slim-bullseye

WORKDIR /app

# Install minimal system dependencies (curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies with pre-built wheels
RUN pip install --upgrade pip setuptools && \
    pip install --no-cache-dir \
    flask==2.3.3 \
    pyyaml>=6.0 \
    boto3==1.28.0 \
    gunicorn==21.2.0

# Copy application code
COPY vpnctl /app/vpnctl

# Copy entrypoint script
COPY vpnctl/health/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create non-root user
RUN useradd -m -u 1000 health && chown -R health:health /app
USER health

# Expose port
EXPOSE 8080

# Mount config as volume
VOLUME ["/app/config"]

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV AWS_REGION=us-east-2
ENV AWS_PROFILE=affinity
# For IRSA (IAM Roles for Service Accounts) in K8s, these are set by K8s:
# AWS_ROLE_ARN - set via service account annotation
# AWS_WEB_IDENTITY_TOKEN_FILE - set via service account token mount

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health/liveness || exit 1

# Run app via entrypoint script
CMD ["/app/entrypoint.sh"]
