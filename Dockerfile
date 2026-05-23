FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data
ENV FINANCE_DB=/app/data/finance.db
ENV HOST=0.0.0.0

EXPOSE 8050

CMD ["python", "app.py"]
