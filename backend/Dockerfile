FROM python:3.11-slim

# System dependencies needed by sentence-transformers, aiomysql, and ChromaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# ChromaDB persistent storage
VOLUME ["/app/chroma_db"]

# Expose FastAPI port
EXPOSE 8000

# Default: run the app with hot-reload (override in docker-compose for prod)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
