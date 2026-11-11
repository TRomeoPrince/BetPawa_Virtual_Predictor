FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PREDICTOR_HEADLESS_ONLY=1 \
    PREDICTOR_DB_PATH=/var/data/predictor.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /var/data

EXPOSE 10000
CMD ["sh", "-c", "python -m backend.deployment_preflight && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
