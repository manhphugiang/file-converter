FROM python:3.11-slim

# Install LibreOffice headless for DOCX to PDF conversion (lighter than LaTeX)
RUN apt-get update && apt-get install -y \
    libreoffice-writer-nogui \
    fonts-liberation \
    fonts-dejavu \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

WORKDIR /app

COPY docx-pdf-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY docx-pdf-service .

RUN mkdir -p /tmp/file-converter

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "main.py"]
