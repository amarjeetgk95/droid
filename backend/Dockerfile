FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    APP_ENV=production \
    DATABASE_URL=""

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml
COPY pyproject.toml .

# Install dependencies (with XGBoost/LightGBM ensemble)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[ml]"

# Copy application source code
COPY app/ ./app/

# Expose port (Cloud Run sets $PORT automatically)
EXPOSE 8000

# Run uvicorn on 0.0.0.0:$PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
