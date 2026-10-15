"""
Lesson service for orchestrating lesson-related business logic.

This module contains the LessonService class that handles complex
operations involving lessons, lesson chunks, file uploads, and content processing.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# FastAPI imports for file upload functionality
from fastapi import UploadFile, HTTPException, status

# Repository imports
from ..repositories.lesson_repository import LessonRepository, LessonChunkRepository
from ..repositories.user_repository import TeacherRepository

# Database scheme imports
from ..DBSchemes.Schemes.lesson import Lesson, LessonChunk
from ..DBSchemes.Schemes.subject import Subject

# Utility imports (will be updated to use dependency injection)
from src.utils.file_validation import FileValidator
from src.utils.pdf_processor import LessonProcessor
from src.utils.embeddings import LessonEmbeddingService


class LessonService:
    """
    Service class for lesson-related business logic.
    
    This class orchestrates operations involving lessons, chunks,
    file uploads, content processing, and related user interactions.
    """
    
    # File upload constraints
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
    ALLOWED_EXTENSIONS = {'.pdf', '.txt'}
    
    # Processing constraints
    MAX_PROCESSING_TIME = 300  # 5 minutes
    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 200
    
    def __init__(self, session: AsyncSession, llm_client=None, vectordb_client=None):
        """
        Initialize the service with database session and optional clients for embedding/vector operations.
        
        Args:
            session: Database session
            llm_client: LLM client from app.embedding_client (for embeddings)
            vectordb_client: VectorDB client from app.vectordb_client (for vector storage)
        """
        self.session = session
        self.lesson_repo = LessonRepository(session)
        self.chunk_repo = LessonChunkRepository(session)
        self.teacher_repo = TeacherRepository(session)
        self.MAX_FILE_SIZE = 25 * 1024 * 1024 
        
        # File processing utilities
        self.file_validator = FileValidator()
        
        # Embedding service (initialized if clients provided)
        if llm_client and vectordb_client:
            self.embedding_service = LessonEmbeddingService(llm_client, vectordb_client, session)
        else:
            self.embedding_service = None
    
    async def create_lesson_with_chunks(
        self, 
        lesson_data: Dict[str, Any], 
        chunks_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create a lesson with its associated chunks in a single transaction.
        
        Args:
            lesson_data: Dictionary with lesson fields
            chunks_data: List of dictionaries with chunk data
            
        Returns:
            Dict with created lesson and chunks
        """
        # Create the lesson
        lesson = await self.lesson_repo.create(**lesson_data)
        
        # Create chunks
        chunks = []
        for chunk_data in chunks_data:
            chunk_data['lesson_id'] = lesson.lesson_id
            chunk = await self.chunk_repo.create(**chunk_data)
            chunks.append(chunk)
        
        return {
            "lesson": lesson,
            "chunks": chunks,
            "total_chunks": len(chunks)
        }
    
    async def get_lesson_with_chunks(self, lesson_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a lesson with all its chunks.
        
        Args:
            lesson_id: UUID of the lesson
            
        Returns:
            Dict with lesson and chunks or None if not found
        """
        lesson = await self.lesson_repo.get_by_id(lesson_id)
        if not lesson:
            return None
        
        chunks = await self.chunk_repo.get_by_lesson_id(lesson_id)
        
        return {
            "lesson": lesson,
            "chunks": chunks,
            "total_chunks": len(chunks)
        }
    
    async def get_teacher_lessons_with_stats(self, teacher_id: UUID) -> Dict[str, Any]:
        """
        Get all lessons for a teacher with statistics.
        
        Args:
            teacher_id: UUID of the teacher
            
        Returns:
            Dict with lessons and statistics
        """
        teacher = await self.teacher_repo.get_by_id(teacher_id)
        lessons = await self.lesson_repo.get_by_teacher_id(teacher_id)
        
        # Calculate statistics
        total_lessons = len(lessons)
        rated_lessons = [l for l in lessons if l.rating is not None]
        avg_rating = sum(l.rating for l in rated_lessons) / len(rated_lessons) if rated_lessons else 0
        
        # Get chunk counts for each lesson
        lessons_with_chunks = []
        for lesson in lessons:
            chunk_count = await self.chunk_repo.get_chunk_count_for_lesson(lesson.lesson_id)
            lessons_with_chunks.append({
                "lesson": lesson,
                "chunk_count": chunk_count
            })
        
        return {
            "teacher": teacher,
            "lessons": lessons_with_chunks,
            "statistics": {
                "total_lessons": total_lessons,
                "average_rating": round(avg_rating, 2),
                "rated_lessons_count": len(rated_lessons)
            }
        }
    
    async def update_lesson_rating(self, lesson_id: UUID, new_rating: float) -> bool:
        """
        Update lesson rating and recalculate teacher's average rating.
        
        Args:
            lesson_id: UUID of the lesson
            new_rating: New rating value
            
        Returns:
            True if updated successfully
        """
        try:
            # Update lesson rating
            lesson = await self.lesson_repo.update(lesson_id, rating=new_rating)
            if not lesson:
                return False
            
            # Get all lessons for this teacher to recalculate average
            teacher_lessons = await self.lesson_repo.get_by_teacher_id(lesson.teacher_id)
            rated_lessons = [l for l in teacher_lessons if l.rating is not None]
            
            if rated_lessons:
                avg_rating = sum(l.rating for l in rated_lessons) / len(rated_lessons)
                await self.teacher_repo.update(lesson.teacher_id, rating=avg_rating)
            
            return True
        except Exception:
            # Let get_db_session handle transaction rollback
            return False
    
    # ==================== TEACHER LESSON UPLOAD FUNCTIONALITY ====================
    
    async def validate_upload_file(self, file: UploadFile) -> bytes:
        """
        Validate and read the uploaded file.
        
        Args:
            file: Uploaded file
            
        Returns:
            File content as bytes
            
        Raises:
            HTTPException: If file validation fails
        """
        try:
            if file.size > self.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File too large. Max size is {self.MAX_FILE_SIZE / (1024 * 1024)} MB"
                )
            # Read file content
            file_content = await file.read()
            
            # Reset file pointer for potential re-reading
            await file.seek(0)
            
            # Validate file
            validation_result = await self.file_validator.validate_and_prepare_file(
                file=file,
                file_content=file_content,
                max_size=self.MAX_FILE_SIZE,
                allowed_extensions=self.ALLOWED_EXTENSIONS
            )
            
            if not validation_result['is_valid']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File validation failed: {validation_result['error']}"
                )
            
            return validation_result['content']
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"File validation error: {str(e)}"
            )
    
    async def create_lesson_record(
        self,
        title: str,
        subject_id: UUID,
        teacher_id: UUID,
        term_id: UUID,
        pdf_url: str = ""
    ) -> Lesson:
        """
        Create a lesson record in the database.
        
        Args:
            title: Lesson title
            subject_id: Subject ID
            teacher_id: Teacher user ID
            term_id: Academic term ID
            pdf_url: URL/path to the PDF file
            
        Returns:
            Created Lesson instance
            
        Raises:
            HTTPException: If lesson creation fails
        """
        try:
            lesson = Lesson(
                lesson_id=uuid4(),
                title=title,
                pdf_url=pdf_url,
                teacher_id=teacher_id,
                subject_id=subject_id,
                term_id=term_id
            )
            
            self.session.add(lesson)
            await self.session.flush()  # Get the ID without committing
            
            return lesson
            
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create lesson record: {str(e)}"
            )
    
    async def process_lesson_content(
        self,
        lesson: Lesson,
        file_content: bytes,
        file_extension: str,
        chunking_strategy: str = "recursive",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Process lesson content: extract text, chunk, generate embeddings, and store.
        
        Args:
            lesson: Lesson database record
            file_content: File content as bytes
            file_extension: File extension (.pdf or .txt)
            chunking_strategy: Text chunking strategy
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            
        Returns:
            Tuple of (success_status, processing_details)
            
        Raises:
            HTTPException: If processing fails
        """
        try:
            # Process file with timeout
            processing_task = asyncio.create_task(
                LessonProcessor.process_lesson_file(
                    file_content=file_content,
                    file_extension=file_extension,
                    lesson_id=lesson.lesson_id,
                    chunking_strategy=chunking_strategy,
                    chunk_size=chunk_size or self.DEFAULT_CHUNK_SIZE,
                    chunk_overlap=chunk_overlap or self.DEFAULT_CHUNK_OVERLAP
                )
            )
            
            # Set timeout for processing
            try:
                full_text, chunk_data_list, file_metadata = await asyncio.wait_for(
                    processing_task, 
                    timeout=self.MAX_PROCESSING_TIME
                )
            except asyncio.TimeoutError:
                processing_task.cancel()
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail="File processing timed out"
                )
            
            # Create lesson chunks in database
            chunks_list = []
            for i, chunk_data in enumerate(chunk_data_list):
                chunk = LessonChunk(
                    chunk_id=uuid4(),
                    lesson_id=lesson.lesson_id,
                    chunk_number=i + 1,
                    chunk_text=chunk_data['chunk_text'],
                    chunk_metadata=chunk_data.get('chunk_metadata', {})
                )
                self.session.add(chunk)
                chunks_list.append(chunk)
            
            # Flush to get database-assigned IDs
            await self.session.flush()
            
            # Store chunks for embeddings processing after commit
            chunks_for_embeddings = []
            for chunk in chunks_list:
                chunk_data = {
                    'chunk_id': chunk.chunk_id,
                    'chunk_text': chunk.chunk_text,
                    'chunk_number': chunk.chunk_number,
                    'chunk_metadata': chunk.chunk_metadata
                }
                chunks_for_embeddings.append(chunk_data)
            
            await self.session.flush()
            
            # Generate comprehensive processing stats (without embeddings yet)
            processing_stats = {
                'lesson_id': str(lesson.lesson_id),
                'file_metadata': file_metadata,
                'text_extraction': {
                    'total_characters': len(full_text),
                    'total_words': len(full_text.split()),
                    'page_count': file_metadata.get('page_count', 0)
                },
                'chunking': {
                    'total_chunks': len(chunk_data_list),
                    'strategy': chunking_strategy,
                    'chunk_size': chunk_size or self.DEFAULT_CHUNK_SIZE,
                    'chunk_overlap': chunk_overlap or self.DEFAULT_CHUNK_OVERLAP
                },
                'embeddings': {'note': 'Processing after database commit'},
                'status': 'success'
            }
            
            return True, processing_stats, chunks_for_embeddings
            
        except HTTPException:
            raise
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Content processing failed: {str(e)}"
            )
    
    async def upload_lesson(
        self,
        file: UploadFile,
        title: str,
        subject_id: UUID,
        teacher_id: UUID,
        term_id: UUID,
        pdf_url: str = "",
        chunking_strategy: str = "recursive",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Complete lesson upload workflow.
        
        Args:
            file: Uploaded file (PDF or TXT)
            title: Lesson title
            subject_id: Subject ID
            teacher_id: Teacher user ID
            term_id: Academic term ID
            pdf_url: URL/path to the file
            chunking_strategy: Text chunking strategy
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            
        Returns:
            Upload result with lesson info and processing stats
            
        Raises:
            HTTPException: If any step fails
        """
        try:
            # Step 1: Validate and read file
            file_content = await self.validate_upload_file(file)
            
            # Get file extension
            import os
            file_extension = os.path.splitext(file.filename)[1].lower()
            
            # Step 2: Get initial file metadata
            from src.utils.pdf_processor import PDFProcessor
            if file_extension == '.pdf':
                file_metadata = PDFProcessor.get_pdf_metadata(file_content)
            else:  # TXT file
                file_metadata = {
                    'file_type': 'txt',
                    'size_bytes': len(file_content),
                    'size_mb': round(len(file_content) / (1024 * 1024), 2),
                    'filename': file.filename
                }
            
            # Step 3: Create lesson record
            lesson = await self.create_lesson_record(
                title=title,
                subject_id=subject_id,
                teacher_id=teacher_id,
                term_id=term_id,
                pdf_url=pdf_url
            )
            
            # Step 4: Process content (extract, chunk, embed, store)
            success, processing_stats, chunks_for_embeddings = await self.process_lesson_content(
                lesson=lesson,
                file_content=file_content,
                file_extension=file_extension,
                chunking_strategy=chunking_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            
            # Step 5: Commit the transaction
            await self.session.commit()
            
            # Step 6: Process embeddings after commit (if embedding service available)
            if self.embedding_service:
                try:
                    success_embed, embedding_stats = await self.embedding_service.process_and_store_lesson(
                        lesson_id=lesson.lesson_id,
                        chunk_data_list=chunks_for_embeddings
                    )
                    
                    if success_embed:
                        processing_stats['embeddings'] = embedding_stats
                    else:
                        processing_stats['embeddings'] = {'error': 'Failed to generate embeddings'}
                        
                except Exception as e:
                    processing_stats['embeddings'] = {'error': f'Embedding processing failed: {str(e)}'}
            else:
                # No embedding service available
                processing_stats['embeddings'] = {'note': 'No embedding service available'}
            
            # Step 7: Return success response
            return {
                'success': True,
                'lesson': {
                    'id': str(lesson.lesson_id),
                    'title': lesson.title,
                    'pdf_url': lesson.pdf_url,
                    'subject_id': str(lesson.subject_id),
                    'teacher_id': str(lesson.teacher_id),
                    'term_id': str(lesson.term_id),
                    'created_at': lesson.created_at.isoformat() if lesson.created_at else None,
                },
                'processing_stats': processing_stats,
                'upload_info': {
                    'filename': file.filename,
                    'file_size': len(file_content),
                    'upload_timestamp': datetime.utcnow().isoformat()
                }
            }
            
        except HTTPException:
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lesson upload failed: {str(e)}"
            )
    
    async def search_lesson_content(
        self,
        teacher_id: UUID,
        query_text: str,
        subject_ids: Optional[List[UUID]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for lesson content using semantic similarity (if embedding service available).
        
        Args:
            teacher_id: Teacher user ID
            query_text: Search query text
            subject_ids: Optional list of subject IDs to filter by
            limit: Maximum number of results
            
        Returns:
            List of matching lesson chunks with similarity scores
        """
        try:
            if not self.embedding_service:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Embedding service not available"
                )
            
            # Get lessons for this teacher (optionally filtered by subjects)
            query = select(Lesson.lesson_id).where(Lesson.teacher_id == teacher_id)
            if subject_ids:
                query = query.where(Lesson.subject_id.in_(subject_ids))
            
            result = await self.session.execute(query)
            lesson_ids = [row[0] for row in result.fetchall()]
            
            # Perform the search
            search_results = await self.embedding_service.search_lesson_content(
                query_text=query_text,
                limit=limit,
                lesson_ids=lesson_ids
            )
            
            # Format results
            formatted_results = []
            for chunk_data, similarity_score in search_results:
                formatted_results.append({
                    'record_id': chunk_data['record_id'],
                    'content': chunk_data['content'],
                    'similarity_score': round(similarity_score, 4),
                    'metadata': chunk_data['metadata']
                })
            
            return formatted_results
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Content search failed: {str(e)}"
            )
    
    async def delete_lesson(self, lesson_id: UUID, teacher_id: UUID) -> Dict[str, Any]:
        """
        Delete a lesson and all its associated data.
        
        Args:
            lesson_id: UUID of the lesson to delete
            teacher_id: UUID of the teacher (for permission check)
            
        Returns:
            Confirmation of deletion with statistics
        """
        try:
            # Check if lesson exists and belongs to the teacher
            result = await self.session.execute(
                select(Lesson).where(
                    Lesson.lesson_id == lesson_id,
                    Lesson.teacher_id == teacher_id
                )
            )
            lesson = result.scalar_one_or_none()
            
            if not lesson:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lesson not found or you don't have permission to delete it."
                )
            
            # Get chunk count before deletion
            chunk_result = await self.session.execute(
                select(LessonChunk).where(LessonChunk.lesson_id == lesson_id)
            )
            chunks = chunk_result.scalars().all()
            chunk_count = len(chunks)
            
            # If embedding service available, clean up vector data first
            if self.embedding_service:
                try:
                    # Delete vectors for each chunk from the vector database
                    for chunk in chunks:
                        # Since the vectordb client might not have a direct delete by chunk_id method,
                        # we need to manually clean up. For now, we'll skip this but note it needs implementation
                        pass
                except Exception as e:
                    # Log the error but continue with deletion
                    print(f"Warning: Could not clean up vector data: {str(e)}")
            
            # Delete vector records manually from lesson_vectors table first
            # This is a workaround until we have proper vector deletion in the embedding service
            from sqlalchemy import text as sql_text
            try:
                # Delete from lesson_vectors where chunk_id matches any of our chunks
                chunk_ids = [str(chunk.chunk_id) for chunk in chunks]
                if chunk_ids:
                    chunk_ids_str = "', '".join(chunk_ids)
                    delete_vectors_sql = sql_text(f"DELETE FROM lesson_vectors WHERE chunk_id IN ('{chunk_ids_str}')")
                    await self.session.execute(delete_vectors_sql)
            except Exception as e:
                print(f"Warning: Could not clean up vector table: {str(e)}")
            
            # Now delete chunks
            for chunk in chunks:
                await self.session.delete(chunk)
            
            # Delete the lesson
            await self.session.delete(lesson)
            await self.session.commit()
            
            return {
                'success': True,
                'message': 'Lesson deleted successfully',
                'deleted_lesson': {
                    'id': str(lesson_id),
                    'title': lesson.title,
                    'deleted_chunks': chunk_count
                }
            }
            
        except HTTPException:
            await self.session.rollback()
            raise
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete lesson: {str(e)}"
            )
    
    async def get_lesson_details(self, lesson_id: UUID, teacher_id: UUID) -> Dict[str, Any]:
        """
        Get detailed information about a specific lesson.
        
        Args:
            lesson_id: UUID of the lesson
            teacher_id: UUID of the teacher (for permission check)
            
        Returns:
            Detailed lesson information
        """
        try:
            # Get lesson details
            result = await self.session.execute(
                select(Lesson, Subject.name.label('subject_name'))
                .join(Subject, Lesson.subject_id == Subject.subject_id)
                .where(
                    Lesson.lesson_id == lesson_id,
                    Lesson.teacher_id == teacher_id
                )
            )
            lesson_data = result.first()
            
            if not lesson_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lesson not found or you don't have permission to view it."
                )
            
            lesson, subject_name = lesson_data
            
            # Get chunk count
            chunk_result = await self.session.execute(
                select(LessonChunk).where(LessonChunk.lesson_id == lesson_id)
            )
            chunks = chunk_result.scalars().all()
            chunk_count = len(chunks)
            
            # Calculate total content length from chunks
            total_content_length = sum(len(chunk.chunk_text) for chunk in chunks)
            total_words = sum(len(chunk.chunk_text.split()) for chunk in chunks)
            
            return {
                'lesson': {
                    'id': str(lesson.lesson_id),
                    'title': lesson.title,
                    'pdf_url': lesson.pdf_url,
                    'subject_id': str(lesson.subject_id),
                    'subject_name': subject_name,
                    'teacher_id': str(lesson.teacher_id),
                    'term_id': str(lesson.term_id),
                    'rating': float(lesson.rating) if lesson.rating else None,
                    'created_at': lesson.created_at.isoformat() if lesson.created_at else None,
                    'updated_at': lesson.updated_at.isoformat() if lesson.updated_at else None,
                },
                'chunks': {
                    'count': chunk_count,
                    'details': [
                        {
                            'chunk_id': str(chunk.chunk_id),
                            'chunk_number': chunk.chunk_number,
                            'content_length': len(chunk.chunk_text),
                            'metadata': chunk.chunk_metadata
                        } for chunk in chunks
                    ]
                },
                'statistics': {
                    'total_characters': total_content_length,
                    'total_words': total_words,
                    'total_chunks': chunk_count,
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get lesson details: {str(e)}"
            )
