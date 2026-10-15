"""
Chat Session Management for temporary conversation storage.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import aioredis

logger = logging.getLogger(__name__)


class ChatSessionManager:
    """
    Manages temporary chat sessions using Redis storage.
    
    This class handles storing and retrieving chat messages for user sessions
    with automatic expiration. Chat messages are not stored permanently
    and are automatically cleaned up after the configured period.
    """
    
    def __init__(self, redis_client: aioredis.Redis, default_ttl: int = 3600):
        """
        Initialize the chat session manager.
        
        Args:
            redis_client: Redis client instance for storage
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self.redis_client = redis_client
        self.default_ttl = default_ttl
        self.logger = logger
        
        # Redis key prefixes for organization
        self.session_prefix = "chat_session"
        self.message_prefix = "chat_messages"
    
    def _get_session_key(self, session_id: str) -> str:
        """
        Generate Redis key for session metadata.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Redis key for session data
        """
        return f"{self.session_prefix}:{session_id}"
    
    def _get_messages_key(self, session_id: str) -> str:
        """
        Generate Redis key for session messages.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Redis key for session messages
        """
        return f"{self.message_prefix}:{session_id}"
    
    async def create_session(self, session_id: str, student_id: str, ttl: Optional[int] = None) -> bool:
        """
        Create a new chat session.
        
        Args:
            session_id: Unique session identifier
            student_id: Student identifier for the session
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            True if session created successfully, False otherwise
        """
        try:
            ttl = ttl or self.default_ttl
            
            session_data = {
                "student_id": student_id,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "message_count": 0
            }
            
            session_key = self._get_session_key(session_id)
            messages_key = self._get_messages_key(session_id)
            
            # Create session metadata
            await self.redis_client.set(
                name=session_key,
                value=json.dumps(session_data),
                ex=ttl
            )
            
            # Initialize empty messages list
            await self.redis_client.delete(messages_key)
            await self.redis_client.expire(messages_key, ttl)
            
            self.logger.info(f"Created chat session {session_id} for student {student_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating session {session_id}: {e}")
            return False
    
    async def add_message(self, session_id: str, message: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Add a message to the chat session.
        
        Args:
            session_id: Session identifier
            message: Message data to store
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            True if message added successfully, False otherwise
        """
        try:
            ttl = ttl or self.default_ttl
            
            # Add timestamp to message
            message_with_timestamp = {
                **message,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            session_key = self._get_session_key(session_id)
            messages_key = self._get_messages_key(session_id)
            
            # Check if session exists
            session_exists = await self.redis_client.exists(session_key)
            if not session_exists:
                self.logger.warning(f"Session {session_id} does not exist")
                return False
            
            # Add message to list
            await self.redis_client.lpush(messages_key, json.dumps(message_with_timestamp))
            await self.redis_client.expire(messages_key, ttl)
            
            # Update session metadata
            await self._update_session_activity(session_id, ttl)
            
            self.logger.debug(f"Added message to session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding message to session {session_id}: {e}")
            return False
    
    async def get_messages(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve messages from the chat session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to retrieve (None for all)
            
        Returns:
            List of messages in chronological order (oldest first)
        """
        try:
            messages_key = self._get_messages_key(session_id)
            
            # Get messages from Redis list (newest first)
            if limit:
                raw_messages = await self.redis_client.lrange(messages_key, 0, limit - 1)
            else:
                raw_messages = await self.redis_client.lrange(messages_key, 0, -1)
            
            # Parse and reverse to get chronological order
            messages = []
            for raw_message in reversed(raw_messages):
                try:
                    message = json.loads(raw_message)
                    messages.append(message)
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to parse message in session {session_id}: {e}")
                    continue
            
            self.logger.debug(f"Retrieved {len(messages)} messages from session {session_id}")
            return messages
            
        except Exception as e:
            self.logger.error(f"Error retrieving messages from session {session_id}: {e}")
            return []
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session metadata.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session metadata or None if session doesn't exist
        """
        try:
            session_key = self._get_session_key(session_id)
            raw_data = await self.redis_client.get(session_key)
            
            if raw_data:
                return json.loads(raw_data)
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting session info for {session_id}: {e}")
            return None
    
    async def session_exists(self, session_id: str) -> bool:
        """
        Check if a chat session exists.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session exists, False otherwise
        """
        try:
            session_key = self._get_session_key(session_id)
            return bool(await self.redis_client.exists(session_key))
            
        except Exception as e:
            self.logger.error(f"Error checking session existence for {session_id}: {e}")
            return False
    
    async def extend_session(self, session_id: str, ttl: Optional[int] = None) -> bool:
        """
        Extend the session expiration time.
        
        Args:
            session_id: Session identifier
            ttl: New time-to-live in seconds (uses default if None)
            
        Returns:
            True if session extended successfully, False otherwise
        """
        try:
            ttl = ttl or self.default_ttl
            
            session_key = self._get_session_key(session_id)
            messages_key = self._get_messages_key(session_id)
            
            # Extend both session metadata and messages
            session_extended = await self.redis_client.expire(session_key, ttl)
            messages_extended = await self.redis_client.expire(messages_key, ttl)
            
            if session_extended:
                await self._update_session_activity(session_id, ttl)
                self.logger.debug(f"Extended session {session_id} for {ttl} seconds")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error extending session {session_id}: {e}")
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a chat session and all its messages.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session deleted successfully, False otherwise
        """
        try:
            session_key = self._get_session_key(session_id)
            messages_key = self._get_messages_key(session_id)
            
            # Delete both session metadata and messages
            session_deleted = await self.redis_client.delete(session_key)
            messages_deleted = await self.redis_client.delete(messages_key)
            
            self.logger.info(f"Deleted session {session_id}")
            return bool(session_deleted or messages_deleted)
            
        except Exception as e:
            self.logger.error(f"Error deleting session {session_id}: {e}")
            return False
    
    async def get_message_count(self, session_id: str) -> int:
        """
        Get the number of messages in a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Number of messages in the session
        """
        try:
            messages_key = self._get_messages_key(session_id)
            return await self.redis_client.llen(messages_key)
            
        except Exception as e:
            self.logger.error(f"Error getting message count for session {session_id}: {e}")
            return 0
    
    async def _update_session_activity(self, session_id: str, ttl: int) -> None:
        """
        Update session last activity timestamp.
        
        Args:
            session_id: Session identifier
            ttl: Time-to-live in seconds
        """
        try:
            session_key = self._get_session_key(session_id)
            session_data = await self.get_session_info(session_id)
            
            if session_data:
                session_data["last_activity"] = datetime.utcnow().isoformat()
                session_data["message_count"] = await self.get_message_count(session_id)
                
                await self.redis_client.set(
                    name=session_key,
                    value=json.dumps(session_data),
                    ex=ttl
                )
                
        except Exception as e:
            self.logger.error(f"Error updating session activity for {session_id}: {e}")
