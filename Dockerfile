# Vision MCP Server - Production Docker Image
# Multi-stage build for minimal footprint

FROM python:3.13-slim AS builder

# Install system dependencies for video processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml ./
COPY src/ ./src/

# Install the package (src/ is now available)
RUN pip install --no-cache-dir .

# Production stage
FROM python:3.13-slim

# Install runtime dependencies for video processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 vision
USER vision

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder --chown=vision:vision /app /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    VISION_MCP_CONFIG=/app/config.yaml

# Expose port for SSE transport
EXPOSE 8000

# Run server via __main__.py entry point
CMD ["python", "-m", "vision_mcp"]