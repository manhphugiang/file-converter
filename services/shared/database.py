"""
Shared database configuration for all microservices
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from typing import Generator
import logging

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration manager"""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "postgresql://fileconverter:fileconverter123@postgres:5432/fileconverter")
        self.pool_size = int(os.getenv("DATABASE_POOL_SIZE", "10"))
        self.max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
        self.pool_timeout = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
        self.echo = os.getenv("DATABASE_ECHO", "false").lower() == "true"
        
        # Create engine with appropriate configuration
        if self.database_url.startswith("sqlite"):
            # SQLite configuration for development
            self.engine = create_engine(
                self.database_url,
                echo=self.echo,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False}
            )
        else:
            # PostgreSQL configuration for production
            self.engine = create_engine(
                self.database_url,
                echo=self.echo,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_pre_ping=True  # Verify connections before use
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database configured: {self.database_url.split('@')[-1] if '@' in self.database_url else self.database_url}")
    
    def create_tables(self):
        """Create all tables and update enums"""
        from .models.job import Base
        from sqlalchemy import text
        
        Base.metadata.create_all(bind=self.engine)
        
        # Add new enum values if they don't exist (for PostgreSQL)
        if not self.database_url.startswith("sqlite"):
            try:
                with self.engine.begin() as conn:
                    # Add 'UPLOADED' to jobstatus enum if it doesn't exist
                    conn.execute(text("""
                        DO $$ 
                        BEGIN 
                            IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'UPLOADED' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'jobstatus')) THEN
                                ALTER TYPE jobstatus ADD VALUE 'UPLOADED' BEFORE 'PENDING';
                            END IF;
                        END $$;
                    """))
                    logger.info("Database enum updated with UPLOADED status")
            except Exception as e:
                logger.warning(f"Could not update enum (may already exist): {e}")
        
        logger.info("Database tables created")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    @contextmanager
    def get_session_context(self) -> Generator[Session, None, None]:
        """Get database session with context manager"""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Global database instance
db_config = DatabaseConfig()


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI to get database session"""
    session = db_config.get_session()
    try:
        yield session
    finally:
        session.close()


def init_database():
    """Initialize database tables"""
    db_config.create_tables()