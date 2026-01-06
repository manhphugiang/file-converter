"""
DOCX to PDF Conversion Worker - LibreOffice headless (lighter than LaTeX)
"""
import os
import sys
import asyncio
import logging
import tempfile
import shutil
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
            task = asyncio.create_task(self._worker_loop(f"docx-pdf-worker-{i}", QueueName.DOCX_PDF))
            self.worker_tasks.append(task)
        logger.info(f"Started {len(self.worker_tasks)} DOCX to PDF workers (LibreOffice)")

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
            
            success, out, err = await self._docx_to_pdf(job_id, message.file_path, message.filename)
            
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

    async def _docx_to_pdf(self, job_id: str, file_path: str, filename: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Convert DOCX to PDF using LibreOffice headless"""
        temp_dir = None
        try:
            # Create a temp directory for this conversion
            temp_dir = tempfile.mkdtemp(dir=self.temp_dir, prefix=f"job_{job_id}_")
            
            # Download input file
            input_file = os.path.join(temp_dir, filename or "input.docx")
            if not storage.download_file(file_path, input_file):
                return False, None, "Failed to download input file"
            
            # Run LibreOffice headless conversion
            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", temp_dir,
                input_file
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "HOME": temp_dir}  # LibreOffice needs HOME
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.conversion_timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return False, None, "Conversion timeout"
            
            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "LibreOffice conversion failed"
                return False, None, error_msg
            
            # Find the output PDF file
            base_name = Path(filename or "input.docx").stem
            output_file = os.path.join(temp_dir, f"{base_name}.pdf")
            
            if not os.path.exists(output_file):
                # Try to find any PDF in the temp dir
                pdf_files = list(Path(temp_dir).glob("*.pdf"))
                if pdf_files:
                    output_file = str(pdf_files[0])
                else:
                    return False, None, "Output PDF not found"
            
            # Upload to MinIO
            output_path = f"converted/{job_id}.pdf"
            if storage.upload_file(output_path, output_file, "application/pdf"):
                return True, output_path, None
            else:
                return False, None, "Failed to upload output file"
                
        except Exception as e:
            logger.error(f"Conversion error for job {job_id}: {e}")
            return False, None, str(e)
        finally:
            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dir: {e}")

    async def _update_status(self, job_id: str, status: JobStatus, **kwargs):
        try:
            with db_config.get_session_context() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = status
                    job.assigned_service = "docx-pdf-service"
                    for k, v in kwargs.items():
                        if hasattr(job, k):
                            setattr(job, k, v)
                    db.commit()
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
