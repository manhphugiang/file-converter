"""
Image Conversion Service - PDF <-> JPG/PNG
Port: 8002
"""
import os
import sys
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.append('/app/shared')
from shared.database import get_db, init_database
from shared.storage import storage
from shared.queue import queue, QueueName
from conversion_worker import ImageConversionWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

conversion_worker = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global conversion_worker
    logger.info("Starting Image Conversion Service...")
    init_database()
    worker_count = int(os.getenv("CONVERSION_WORKERS", "2"))
    conversion_worker = ImageConversionWorker(worker_count=worker_count)
    await conversion_worker.start()
    logger.info("Image Conversion Service started")
    yield
    if conversion_worker:
        await conversion_worker.stop()
    logger.info("Image Conversion Service stopped")

app = FastAPI(title="Image Conversion Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health_check():
    try:
        queue.redis_client.ping()
        storage.client.list_buckets()
        return {"status": "healthy", "service": "image-service"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
