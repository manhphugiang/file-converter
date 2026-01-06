"""
Shared job models for all microservices
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from enum import Enum
from datetime import datetime
from typing import Optional

Base = declarative_base()


class JobStatus(Enum):
    """Job status enumeration"""
    UPLOADED = "uploaded"      # File stored in MinIO, not yet queued
    PENDING = "pending"        # Queued in Redis, waiting for worker
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConversionType(Enum):
    """Conversion type enumeration"""
    DOCX_TO_PDF = "docx_to_pdf"
    PDF_TO_DOCX = "pdf_to_docx"
    PDF_TO_JPG = "pdf_to_jpg"
    PDF_TO_PNG = "pdf_to_png"
    JPG_TO_PDF = "jpg_to_pdf"
    PNG_TO_PDF = "png_to_pdf"


class Job(Base):
    """
    Shared job model for all conversion services
    """
    __tablename__ = "jobs"
    
    # Primary fields
    id = Column(String(36), primary_key=True)  # UUID
    filename = Column(String(255), nullable=False)
    conversion_type = Column(SQLEnum(ConversionType), nullable=False)
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING)
    
    # File information
    original_size = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)  # MinIO path for input file
    output_path = Column(String(500), nullable=True)  # MinIO path for output file
    
    # Service assignment
    assigned_service = Column(String(50), nullable=True)  # Which service is processing
    worker_id = Column(String(50), nullable=True)  # Which worker instance
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Metadata
    client_ip = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(64), nullable=True)  # Session tracking
    
    def __repr__(self):
        return f"<Job(id='{self.id}', type='{self.conversion_type}', status='{self.status}')>"
    
    def to_dict(self):
        """Convert job to dictionary for API responses"""
        return {
            "id": self.id,
            "filename": self.filename,
            "conversion_type": self.conversion_type.value,
            "status": self.status.value,
            "original_size": self.original_size,
            "file_path": self.file_path,
            "output_path": self.output_path,
            "assigned_service": self.assigned_service,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }
    
    def is_expired(self, expiry_hours: int = 24) -> bool:
        """Check if job is expired"""
        if not self.created_at:
            return False
        
        from datetime import timedelta
        expiry_time = self.created_at + timedelta(hours=expiry_hours)
        return datetime.utcnow() > expiry_time
    
    def can_retry(self) -> bool:
        """Check if job can be retried"""
        return self.retry_count < self.max_retries and self.status == JobStatus.FAILED