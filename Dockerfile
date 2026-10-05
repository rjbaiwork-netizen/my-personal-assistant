FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app
RUN mkdir -p /app/storage/excel_files /app/storage/backups

EXPOSE 10000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "10000"]