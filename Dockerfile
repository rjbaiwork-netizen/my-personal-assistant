FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

COPY . /app

RUN mkdir -p /app/storage/excel_files /app/storage/backups

EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.ai_app:app --host 0.0.0.0 --port ${PORT:-7860}"]
