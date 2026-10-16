# Python image shared by the log generator and the API/dashboard.
FROM python:3.12-slim

WORKDIR /app
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt
COPY sentinellake ./sentinellake
COPY api ./api
ENV PYTHONUNBUFFERED=1 TZ=UTC
