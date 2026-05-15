# Step 15: container for Google Cloud Run / Fly / Render deployment.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies required for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel to ensure binary packages are preferred
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --prefer-binary -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY sql ./sql

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
