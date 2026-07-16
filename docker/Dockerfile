FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directories
RUN mkdir -p data/raw data/processed data/exports

# Expose ports
EXPOSE 8501 8000

# Default command (can be overridden)
CMD ["streamlit", "run", "app/dashboard/run.py", "--server.port=8501", "--server.address=0.0.0.0"]