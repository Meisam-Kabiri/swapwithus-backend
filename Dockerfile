FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package in editable mode (same as local dev)
RUN pip install -e .

# Cloud Run will set PORT environment variable
ENV PORT=8080

# Expose port
EXPOSE 8080

# Run the application using absolute import path
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
