FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py models.py routes.py db.py news_fetcher.py diary_service.py memory_loader.py affinity_tracker.py ./
COPY static/ static/
COPY memory/ memory/

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
