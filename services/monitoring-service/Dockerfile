FROM node:18-alpine AS frontend-builder

WORKDIR /frontend
COPY monitoring-service/frontend/package*.json ./
RUN npm install
COPY monitoring-service/frontend/ ./
RUN npm run build

FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl gcc python3-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY monitoring-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitoring-service/main.py .
COPY --from=frontend-builder /frontend/build /app/static

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["python", "main.py"]
