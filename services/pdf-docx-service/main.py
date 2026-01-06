"""
PDF to DOCX Service - Lightweight pdf2docx only
Port: 8002
"""
import os
import sys
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

sys.path.append('/app/shared')
from conversion_worker import ConversionWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

worker = ConversionWorker(worker_count=int(os.getenv("CONVERSION_WORKERS", "3")))

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting PDF to DOCX Service...")
    await worker.start()
    logger.info("PDF to DOCX Service started")
    yield
    await worker.stop()
    logger.info("PDF to DOCX Service stopped")

app = FastAPI(title="PDF to DOCX Service", version="1.0.0", lifespan=lifespan)

@app.get("/")
async def root():
    return {"service": "PDF to DOCX Service", "version": "1.0.0", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "pdf-docx-service", "active_jobs": len(worker.active_jobs)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8002")), reload=False)
