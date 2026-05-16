FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite databases
RUN mkdir -p /app/data
ENV FINANCE_DB=/app/data/finance.db
ENV DAILY_EDGE_DB=/app/data/daily_edge_cache.db

EXPOSE 8050

CMD ["python", "app.py"]
