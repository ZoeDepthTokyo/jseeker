# =============================================================================
# jSeeker -- The Shape-Shifting Resume Engine
# Self-contained Docker image (includes MYCEL from GitHub)
# =============================================================================
FROM python:3.11-slim AS base

# System deps for WeasyPrint (PDF generation) and PyMuPDF (PDF preview)
# curl is needed by the HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libcairo2-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# Playwright browser binaries are large; install chromium only if auto-apply is needed.
# Set PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 for headless-only or API-only deployments.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install MYCEL from GitHub (self-contained -- no local path dependency)
RUN pip install --no-cache-dir git+https://github.com/ZoeDepthTokyo/gaia-mycel.git

# Install Playwright browser (chromium only) for ATS automation.
# Remove this block if auto-apply features are not needed in production.
RUN python -m playwright install chromium --with-deps

# Copy application code (excludes everything in .dockerignore)
COPY . .

# Create data and output directories if they do not already exist in the image
RUN mkdir -p /app/data /app/output

# Runtime environment -- all values can be overridden via docker run -e or compose env:
ENV STREAMLIT_SERVER_PORT=8502
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8502

# Lightweight health check against Streamlit's built-in health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

# Entry point matches run.py: APP_ENTRY = PROJECT_ROOT / "ui" / "app.py"
CMD ["python", "-m", "streamlit", "run", "ui/app.py", \
     "--server.port=8502", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
