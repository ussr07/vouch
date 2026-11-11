# Vouch: the FastAPI server and the web page. Bifrost runs in its own container
# (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vouch ./vouch
COPY app ./app
COPY scripts ./scripts
COPY eval ./eval

# Saved briefs and the search cache live in /app/data (a volume in docker-compose.yml).
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
