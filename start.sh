#!/bin/sh
# Start script for Railway deployment
# Handles PORT variable expansion

# Default to 8080 if PORT is not set
PORT="${PORT:-8080}"

echo "Starting ViralClip on port $PORT"
exec uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
