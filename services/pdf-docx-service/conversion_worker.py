"""
PDF to DOCX Conversion Worker - pdf2docx only (lightweight)
"""
import os
import sys
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Set, Optional
from datetime import datetime

sys.path.append('/app/shared')
from shared.models.job import Job, JobStatus, ConversionType
from shared.database import db_config
from shared.storage import storage
from shared.queue import queue, QueueName, QueueMessage

logger = logging.getLogger(__name__)


class ConversionWorker:
    def __init__(self, worker_count: int = 3):
        self.worker_count = worker_count
        self.is_running = False
        self.active_jobs: Set[str] = set()
        self.worker_tasks = []
        self.conversion_timeout = int(os.getenv("CONVERSION_TIMEOUT", "60"))
        self.temp_dir = os.getenv("TEMP_DIR", "/tmp/file-converter")
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        for i in range(self.worker_count):
            task = asyncio.create_task(self._worker_loop(f"pdf-docx-worker-{i}", QueueName.PDF_DOCX))
            self.worker_tasks.append(task)
        logger.info(f"Started {len(self.worker_tasks)} PDF to DOCX workers")

    async def stop(self):
        self.is_running = False
        for task in self.worker_tasks:
            task.cancel()
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()

    async def _worker_loop(self, worker_id: str, queue_name: QueueName):
        logger.info(f"Worker {worker_id} started for {queue_name.value}")
        while self.is_running:
            try:
                loop = asyncio.get_event_loop()
                message = await loop.run_in_executor(None, lambda: queue.dequeue(queue_name, timeout=5))
                if message:
                    await self._process_job(worker_id, message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

    async def _process_job(self, worker_id: str, message: QueueMessage):
        job_id = message.job_id
        try:
            self.active_jobs.add(job_id)
            await self._update_status(job_id, JobStatus.PROCESSING, worker_id=worker_id, started_at=datetime.utcnow())
            
            success, out, err = await self._pdf_to_docx(job_id, message.file_path)
            
            if success:
                await self._update_status(job_id, JobStatus.COMPLETED, output_path=out, completed_at=datetime.utcnow())
                logger.info(f"Job {job_id} completed")
            else:
                await self._update_status(job_id, JobStatus.FAILED, error_message=err, completed_at=datetime.utcnow())
                logger.error(f"Job {job_id} failed: {err}")
        except Exception as e:
            await self._update_status(job_id, JobStatus.FAILED, error_message=str(e), completed_at=datetime.utcnow())
        finally:
            self.active_jobs.discard(job_id)

    async def _pdf_to_docx(self, job_id: str, file_path: str) -> tuple[bool, Optional[str], Optional[str]]:
        temp_in = temp_out = None
        try:
            temp_in = storage.download_to_temp(file_path, suffix=".pdf")
            if not temp_in:
                return False, None, "Failed to download"
            fd, temp_out = tempfile.mkstemp(suffix=".docx", dir=self.temp_dir)
            os.close(fd)
            
            loop = asyncio.get_event_loop()
            def convert():
                from pdf2docx import Converter
                cv = Converter(temp_in)
                cv.convert(temp_out)
                cv.close()
            
            await asyncio.wait_for(loop.run_in_executor(None, convert), timeout=self.conversion_timeout)
            
            if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                out_path = f"converted/{job_id}.docx"
                if storage.upload_file(out_path, temp_out, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
                    return True, out_path, None
            return False, None, "Conversion failed"
        except Exception as e:
            return False, None, str(e)
        finally:
            if temp_in: Path(temp_in).unlink(missing_ok=True)
            if temp_out: Path(temp_out).unlink(missing_ok=True)

    async def _update_status(self, job_id: str, status: JobStatus, **kwargs):
        try:
            with db_config.get_session_context() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = status
                    job.assigned_service = "pdf-docx-service"
                    for k, v in kwargs.items():
                        if hasattr(job, k):
                            setattr(job, k, v)
                    db.commit()
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
