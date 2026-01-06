"""
Shared Redis queue for microservices communication
"""
import os
import json
import redis
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class QueueName(Enum):
    """Queue names for different services"""
    DOCX_PDF = "queue:docx_pdf"
    PDF_DOCX = "queue:pdf_docx"
    PDF_IMAGE = "queue:pdf_image"
    IMAGE_PDF = "queue:image_pdf"
    NOTIFICATIONS = "queue:notifications"


@dataclass
class QueueMessage:
    """Standard message format for all queues"""
    job_id: str
    conversion_type: str
    file_path: str
    filename: str
    priority: int = 0
    retry_count: int = 0
    metadata: Dict[str, Any] = None
    
    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'QueueMessage':
        """Create message from JSON string"""
        data = json.loads(json_str)
        return cls(**data)


class RedisQueue:
    """Redis-based queue manager for microservices"""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        
        # Test connection
        try:
            self.redis_client.ping()
            logger.info(f"Redis connected: {self.redis_url}")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    def enqueue(self, queue_name: QueueName, message: QueueMessage) -> bool:
        """Add message to queue"""
        try:
            # Use priority queue (sorted set) for better job ordering
            score = -message.priority  # Negative for descending order
            result = self.redis_client.zadd(
                queue_name.value,
                {message.to_json(): score}
            )
            
            if result:
                logger.info(f"Enqueued job {message.job_id} to {queue_name.value}")
                return True
            else:
                logger.warning(f"Job {message.job_id} already in queue {queue_name.value}")
                return False
                
        except Exception as e:
            logger.error(f"Error enqueuing job {message.job_id}: {e}")
            return False
    
    def dequeue(self, queue_name: QueueName, timeout: int = 10) -> Optional[QueueMessage]:
        """Get message from queue (blocking)"""
        try:
            # Use BZPOPMAX for blocking pop with highest priority
            result = self.redis_client.bzpopmax(queue_name.value, timeout=timeout)
            
            if result:
                queue_key, message_json, score = result
                message = QueueMessage.from_json(message_json)
                logger.info(f"Dequeued job {message.job_id} from {queue_name.value}")
                return message
            else:
                return None  # Timeout
                
        except Exception as e:
            logger.error(f"Error dequeuing from {queue_name.value}: {e}")
            return None
    
    def peek(self, queue_name: QueueName, count: int = 10) -> List[QueueMessage]:
        """Peek at messages in queue without removing them"""
        try:
            # Get top messages by score (highest priority first)
            results = self.redis_client.zrevrange(
                queue_name.value, 0, count - 1, withscores=True
            )
            
            messages = []
            for message_json, score in results:
                message = QueueMessage.from_json(message_json)
                messages.append(message)
            
            return messages
            
        except Exception as e:
            logger.error(f"Error peeking at {queue_name.value}: {e}")
            return []
    
    def get_queue_size(self, queue_name: QueueName) -> int:
        """Get number of messages in queue"""
        try:
            return self.redis_client.zcard(queue_name.value)
        except Exception as e:
            logger.error(f"Error getting queue size for {queue_name.value}: {e}")
            return 0
    
    def remove_job(self, queue_name: QueueName, job_id: str) -> bool:
        """Remove specific job from queue"""
        try:
            # Get all messages and find the one with matching job_id
            messages = self.redis_client.zrange(queue_name.value, 0, -1)
            
            for message_json in messages:
                message = QueueMessage.from_json(message_json)
                if message.job_id == job_id:
                    result = self.redis_client.zrem(queue_name.value, message_json)
                    if result:
                        logger.info(f"Removed job {job_id} from {queue_name.value}")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error removing job {job_id} from {queue_name.value}: {e}")
            return False
    
    def clear_queue(self, queue_name: QueueName) -> bool:
        """Clear all messages from queue"""
        try:
            result = self.redis_client.delete(queue_name.value)
            logger.info(f"Cleared queue {queue_name.value}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error clearing queue {queue_name.value}: {e}")
            return False
    
    def get_all_queue_stats(self) -> Dict[str, int]:
        """Get statistics for all queues"""
        stats = {}
        for queue_name in QueueName:
            stats[queue_name.value] = self.get_queue_size(queue_name)
        return stats
    
    def publish_notification(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish notification to Redis pub/sub channel"""
        try:
            result = self.redis_client.publish(channel, json.dumps(message))
            logger.info(f"Published notification to {channel}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error publishing notification to {channel}: {e}")
            return False
    
    def subscribe_notifications(self, channels: List[str]):
        """Subscribe to notification channels"""
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(*channels)
            logger.info(f"Subscribed to channels: {channels}")
            return pubsub
        except Exception as e:
            logger.error(f"Error subscribing to channels {channels}: {e}")
            return None


# Global queue instance
queue = RedisQueue()