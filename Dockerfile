# ViralClip - Viral Content Automation Platform
# Lightweight production build for Railway

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install requirements (production-only, lightweight)
COPY backend/requirements-prod.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create directories for processing
RUN mkdir -p output temp data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8080

# Start command is defined in railway.json
