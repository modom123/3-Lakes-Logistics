# 3 Lakes Logistics — FastAPI container.
# Three modes via RUN_MODE env var:
#   api       → uvicorn (default)
#   worker    → python -m app.worker
#   scheduler → python -m app.scheduler
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RUN_MODE=api

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY sql ./sql

EXPOSE 8080

CMD ["sh", "-c", "\
 if [ \"$RUN_MODE\" = worker ]; then exec python -m app.worker; \
 elif [ \"$RUN_MODE\" = scheduler ]; then exec python -m app.scheduler; \
 else exec uvicorn app.main:app --host 0.0.0.0 --port 8080; fi"]
