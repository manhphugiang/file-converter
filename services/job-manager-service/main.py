"""
Job Manager Service - Central job orchestration
Port: 8010
"""
import os
import sys
import logging
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request, Response, Form, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import uvicorn

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from shared.models.job import Job, JobStatus, ConversionType
from shared.database import get_db, init_database
from shared.storage import storage
from shared.queue import queue, QueueName, QueueMessage

# API Router with /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Job Manager Service...")
    
    # Initialize database
    init_database()
    
    logger.info("Job Manager Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Job Manager Service stopped")


# Create FastAPI app
app = FastAPI(
    title="File Converter - Job Manager",
    version="1.0.0",
    description="Central job orchestration and management service",
    lifespan=lifespan
)

# Add CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def get_or_create_session_id(request: Request, response: Response) -> str:
    """Get existing session ID from cookie or create a new one"""
    session_id = request.cookies.get("session_id")
    
    if not session_id:
        # Generate a new session ID
        session_id = hashlib.sha256(f"{uuid.uuid4()}{datetime.utcnow()}".encode()).hexdigest()[:32]
        # Set cookie that expires in 30 days
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=30 * 24 * 60 * 60,  # 30 days
            httponly=True,
            samesite="lax"
        )
    
    return session_id


@app.get("/")
async def root():
    """Service information"""
    return {
        "service": "File Converter - Job Manager",
        "version": "1.0.0",
        "status": "running",
        "description": "Central job orchestration and management"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        with next(get_db()) as db:
            db.execute("SELECT 1")
        
        # Check Redis connection
        queue.redis_client.ping()
        
        # Check MinIO connection
        storage.client.list_buckets()
        
        return {
            "status": "healthy",
            "service": "job-manager-service",
            "database": "connected",
            "redis": "connected",
            "storage": "connected",
            "queue_stats": queue.get_all_queue_stats()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    conversion_type: Optional[str] = Form(None),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    """
    Upload file and create conversion job.
    Flow: Upload to MinIO first (fast) -> Create DB record -> Queue to Redis (async)
    User gets immediate response after MinIO upload, doesn't wait for Redis.
    """
    try:
        # Get or create session ID
        session_id = get_or_create_session_id(request, response)
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Determine conversion type based on file extension or explicit parameter
        filename_lower = file.filename.lower()
        
        # Map of conversion types to queues
        conversion_map = {
            'docx_to_pdf': (ConversionType.DOCX_TO_PDF, QueueName.DOCX_PDF),
            'pdf_to_docx': (ConversionType.PDF_TO_DOCX, QueueName.PDF_DOCX),
            'pdf_to_jpg': (ConversionType.PDF_TO_JPG, QueueName.PDF_IMAGE),
            'pdf_to_png': (ConversionType.PDF_TO_PNG, QueueName.PDF_IMAGE),
            'jpg_to_pdf': (ConversionType.JPG_TO_PDF, QueueName.IMAGE_PDF),
            'png_to_pdf': (ConversionType.PNG_TO_PDF, QueueName.IMAGE_PDF),
        }
        
        if conversion_type and conversion_type in conversion_map:
            conv_type, queue_name = conversion_map[conversion_type]
        elif filename_lower.endswith('.docx'):
            conv_type, queue_name = ConversionType.DOCX_TO_PDF, QueueName.DOCX_PDF
        elif filename_lower.endswith('.pdf'):
            conv_type, queue_name = ConversionType.PDF_TO_DOCX, QueueName.PDF_DOCX
        elif filename_lower.endswith(('.jpg', '.jpeg')):
            conv_type, queue_name = ConversionType.JPG_TO_PDF, QueueName.IMAGE_PDF
        elif filename_lower.endswith('.png'):
            conv_type, queue_name = ConversionType.PNG_TO_PDF, QueueName.IMAGE_PDF
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Supported: .docx, .pdf, .jpg, .png"
            )
        
        # Check file size
        max_size = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {max_size // (1024*1024)}MB"
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # STEP 1: Upload file to MinIO FIRST (this is the priority)
        file_path = f"uploads/{job_id}_{file.filename}"
        
        from io import BytesIO
        success = storage.upload_data(
            object_name=file_path,
            data=BytesIO(file_content),
            length=len(file_content),
            content_type=file.content_type
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upload file to storage")
        
        # STEP 2: Create job record with UPLOADED status (file is safe in MinIO)
        job = Job(
            id=job_id,
            filename=file.filename,
            conversion_type=conv_type,
            status=JobStatus.UPLOADED,  # File stored, not yet queued
            original_size=len(file_content),
            file_path=file_path,
            client_ip=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            session_id=session_id
        )
        
        db.add(job)
        db.commit()
        
        logger.info(f"File uploaded to MinIO for job {job_id}, now queuing...")
        
        # STEP 3: Queue to Redis (non-blocking for user, file is already safe)
        message = QueueMessage(
            job_id=job_id,
            conversion_type=conv_type.value,
            file_path=file_path,
            filename=file.filename,
            priority=1,
            metadata={
                "original_size": len(file_content),
                "client_ip": job.client_ip
            }
        )
        
        queue_success = queue.enqueue(queue_name, message)
        
        if queue_success:
            # Update status to PENDING (queued successfully)
            job.status = JobStatus.PENDING
            db.commit()
            logger.info(f"Job {job_id} queued successfully")
        else:
            # Redis queue failed, but file is safe in MinIO
            # Job stays as UPLOADED - can be retried later
            logger.warning(f"Failed to queue job {job_id} to Redis, file is safe in MinIO with status UPLOADED")
        
        return {
            "job_id": job_id,
            "filename": file.filename,
            "conversion_type": conv_type.value,
            "status": job.status.value,
            "message": "File uploaded successfully" if job.status == JobStatus.UPLOADED else "File uploaded and conversion queued successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/status/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get job status"""
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/download/{job_id}")
async def download_file(job_id: str, db: Session = Depends(get_db)):
    """Download converted file"""
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Job not completed. Current status: {job.status.value}"
            )
        
        if not job.output_path:
            raise HTTPException(status_code=404, detail="Output file not found")
        
        # Get file from MinIO
        file_obj = storage.get_object(job.output_path)
        
        if not file_obj:
            raise HTTPException(status_code=404, detail="File not found in storage")
        
        # Determine output filename and content type based on conversion type
        base_name = os.path.splitext(job.filename)[0]
        
        output_map = {
            ConversionType.DOCX_TO_PDF: (f"{base_name}.pdf", "application/pdf"),
            ConversionType.PDF_TO_DOCX: (f"{base_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ConversionType.PDF_TO_JPG: (f"{base_name}.jpg", "image/jpeg"),
            ConversionType.PDF_TO_PNG: (f"{base_name}.png", "image/png"),
            ConversionType.JPG_TO_PDF: (f"{base_name}.pdf", "application/pdf"),
            ConversionType.PNG_TO_PDF: (f"{base_name}.pdf", "application/pdf"),
        }
        
        # Check if output is a zip (multi-page PDF to images)
        if job.output_path and job.output_path.endswith('.zip'):
            output_filename = f"{base_name}_pages.zip"
            content_type = "application/zip"
        elif job.conversion_type in output_map:
            output_filename, content_type = output_map[job.conversion_type]
        else:
            output_filename = f"converted_{job.filename}"
            content_type = "application/octet-stream"
        
        # Stream file response
        def generate():
            try:
                while True:
                    chunk = file_obj.read(8192)
                    if not chunk:
                        break
                    yield chunk
            finally:
                file_obj.close()
        
        headers = {
            "Content-Disposition": f"attachment; filename={output_filename}"
        }
        
        return StreamingResponse(
            generate(),
            media_type=content_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    conversion_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List jobs with optional filtering"""
    try:
        query = db.query(Job)
        
        # Apply filters
        if status:
            try:
                status_enum = JobStatus(status)
                query = query.filter(Job.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if conversion_type:
            try:
                type_enum = ConversionType(conversion_type)
                query = query.filter(Job.conversion_type == type_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid conversion type: {conversion_type}")
        
        # Apply pagination
        jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "jobs": [job.to_dict() for job in jobs],
            "total": query.count(),
            "limit": limit,
            "offset": offset
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/session/jobs")
async def list_session_jobs(
    request: Request,
    response: Response,
    status: Optional[str] = None,
    conversion_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List jobs for current session"""
    try:
        # Get session ID
        session_id = get_or_create_session_id(request, response)
        
        query = db.query(Job).filter(Job.session_id == session_id)
        
        # Apply filters
        if status:
            try:
                status_enum = JobStatus(status)
                query = query.filter(Job.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if conversion_type:
            try:
                type_enum = ConversionType(conversion_type)
                query = query.filter(Job.conversion_type == type_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid conversion type: {conversion_type}")
        
        # Apply pagination
        jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "jobs": [job.to_dict() for job in jobs],
            "total": query.count(),
            "limit": limit,
            "offset": offset,
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing session jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """Cancel a job"""
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status: {job.status.value}"
            )
        
        # Remove from queue if pending
        if job.status == JobStatus.PENDING:
            # Determine queue based on conversion type
            if job.conversion_type == ConversionType.DOCX_TO_PDF:
                queue_name = QueueName.DOCX_PDF
            elif job.conversion_type == ConversionType.PDF_TO_DOCX:
                queue_name = QueueName.PDF_DOCX
            elif job.conversion_type == ConversionType.MP4_TO_MP3:
                queue_name = QueueName.MP4_MP3
            else:
                queue_name = QueueName.DOCX_PDF  # Default
            
            queue.remove_job(queue_name, job_id)
        
        # Update job status
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Cancelled job {job_id}")
        
        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job cancelled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/admin/queue/status")
async def get_all_queue_status():
    """Get status of all queues"""
    try:
        return {
            "service": "job-manager-service",
            "queues": queue.get_all_queue_stats(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/admin/retry-uploaded")
async def retry_uploaded_jobs(db: Session = Depends(get_db)):
    """
    Retry queuing jobs that are stuck in UPLOADED status.
    These are jobs where file was uploaded to MinIO but Redis queue failed.
    """
    try:
        # Find all jobs with UPLOADED status
        uploaded_jobs = db.query(Job).filter(Job.status == JobStatus.UPLOADED).all()
        
        if not uploaded_jobs:
            return {
                "message": "No uploaded jobs to retry",
                "retried": 0,
                "failed": 0
            }
        
        # Map conversion types to queues
        queue_map = {
            ConversionType.DOCX_TO_PDF: QueueName.DOCX_PDF,
            ConversionType.PDF_TO_DOCX: QueueName.PDF_DOCX,
            ConversionType.PDF_TO_JPG: QueueName.PDF_IMAGE,
            ConversionType.PDF_TO_PNG: QueueName.PDF_IMAGE,
            ConversionType.JPG_TO_PDF: QueueName.IMAGE_PDF,
            ConversionType.PNG_TO_PDF: QueueName.IMAGE_PDF,
        }
        
        retried = 0
        failed = 0
        
        for job in uploaded_jobs:
            try:
                queue_name = queue_map.get(job.conversion_type)
                if not queue_name:
                    logger.warning(f"Unknown conversion type for job {job.id}: {job.conversion_type}")
                    failed += 1
                    continue
                
                message = QueueMessage(
                    job_id=job.id,
                    conversion_type=job.conversion_type.value,
                    file_path=job.file_path,
                    filename=job.filename,
                    priority=1,
                    metadata={
                        "original_size": job.original_size,
                        "client_ip": job.client_ip,
                        "retry": True
                    }
                )
                
                if queue.enqueue(queue_name, message):
                    job.status = JobStatus.PENDING
                    retried += 1
                    logger.info(f"Retried job {job.id}")
                else:
                    failed += 1
                    logger.warning(f"Failed to retry job {job.id}")
                    
            except Exception as e:
                logger.error(f"Error retrying job {job.id}: {e}")
                failed += 1
        
        db.commit()
        
        return {
            "message": f"Retry complete: {retried} queued, {failed} failed",
            "retried": retried,
            "failed": failed,
            "total_uploaded": len(uploaded_jobs)
        }
        
    except Exception as e:
        logger.error(f"Error retrying uploaded jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/admin/cleanup")
async def cleanup_expired_jobs(db: Session = Depends(get_db)):
    """Clean up expired jobs and files"""
    try:
        expiry_hours = int(os.getenv("JOB_EXPIRY_HOURS", "24"))
        failed_expiry_hours = int(os.getenv("FAILED_JOB_EXPIRY_HOURS", "6"))
        
        cutoff_time = datetime.utcnow() - timedelta(hours=expiry_hours)
        failed_cutoff_time = datetime.utcnow() - timedelta(hours=failed_expiry_hours)
        
        # Find expired jobs
        expired_jobs = db.query(Job).filter(
            or_(
                and_(Job.created_at < cutoff_time, Job.status.in_([JobStatus.COMPLETED, JobStatus.CANCELLED])),
                and_(Job.created_at < failed_cutoff_time, Job.status == JobStatus.FAILED)
            )
        ).all()
        
        cleaned_count = 0
        for job in expired_jobs:
            try:
                # Delete files from storage
                if job.file_path:
                    storage.delete_object(job.file_path)
                if job.output_path:
                    storage.delete_object(job.output_path)
                
                # Delete job record
                db.delete(job)
                cleaned_count += 1
                
            except Exception as e:
                logger.error(f"Error cleaning up job {job.id}: {e}")
        
        db.commit()
        
        logger.info(f"Cleaned up {cleaned_count} expired jobs")
        
        return {
            "cleaned_jobs": cleaned_count,
            "expiry_hours": expiry_hours,
            "failed_expiry_hours": failed_expiry_hours,
            "message": f"Successfully cleaned up {cleaned_count} expired jobs"
        }
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8010"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true"
    )