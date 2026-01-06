"""
Shared MinIO storage client for all microservices
"""
import os
import logging
from minio import Minio
from minio.error import S3Error
from typing import Optional, BinaryIO
from urllib.parse import urlparse
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageConfig:
    """MinIO storage configuration"""
    
    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        self.secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        self.bucket_name = os.getenv("MINIO_BUCKET_NAME", "file-converter")
        self.region = os.getenv("MINIO_REGION", "us-east-1")
        
        # Create MinIO client
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            region=self.region
        )
        
        # Ensure bucket exists
        self._ensure_bucket_exists()
        
        logger.info(f"MinIO storage configured: {self.endpoint}")
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name, location=self.region)
                logger.info(f"Created MinIO bucket: {self.bucket_name}")
            else:
                logger.info(f"MinIO bucket exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error ensuring bucket exists: {e}")
            raise
    
    def upload_file(self, object_name: str, file_path: str, content_type: str = None) -> bool:
        """Upload file to MinIO"""
        try:
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=file_path,
                content_type=content_type
            )
            logger.info(f"Uploaded file: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error uploading file {object_name}: {e}")
            return False
    
    def upload_data(self, object_name: str, data: BinaryIO, length: int, content_type: str = None) -> bool:
        """Upload data stream to MinIO"""
        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type
            )
            logger.info(f"Uploaded data: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error uploading data {object_name}: {e}")
            return False
    
    def download_file(self, object_name: str, file_path: str) -> bool:
        """Download file from MinIO"""
        try:
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            logger.info(f"Downloaded file: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error downloading file {object_name}: {e}")
            return False
    
    def get_object(self, object_name: str) -> Optional[BinaryIO]:
        """Get object data stream from MinIO"""
        try:
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            return response
        except S3Error as e:
            logger.error(f"Error getting object {object_name}: {e}")
            return None
    
    def delete_object(self, object_name: str) -> bool:
        """Delete object from MinIO"""
        try:
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            logger.info(f"Deleted object: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error deleting object {object_name}: {e}")
            return False
    
    def object_exists(self, object_name: str) -> bool:
        """Check if object exists in MinIO"""
        try:
            self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            return True
        except S3Error:
            return False
    
    def get_presigned_url(self, object_name: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Get presigned URL for object download"""
        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=expires_in_seconds
            )
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL for {object_name}: {e}")
            return None
    
    def download_to_temp(self, object_name: str, suffix: str = None) -> Optional[str]:
        """Download object to temporary file and return path"""
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
            os.close(temp_fd)  # Close file descriptor, keep path
            
            # Download to temp file
            if self.download_file(object_name, temp_path):
                return temp_path
            else:
                # Clean up on failure
                Path(temp_path).unlink(missing_ok=True)
                return None
                
        except Exception as e:
            logger.error(f"Error downloading to temp file: {e}")
            return None


# Global storage instance
storage = StorageConfig()