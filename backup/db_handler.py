from sqlalchemy.orm import Session
from datetime import datetime
import json
from typing import List, Dict, Any
from database import Session as DBSession, Speaker, Segment, RefinedSegment
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseHandler:
    def __init__(self):
        self.db = DBSession()

    def store_segment(self, data: Dict[str, Any]) -> bool:
        """Store a single segment of data"""
        try:
            # First, ensure session exists
            session = self.db.query(Session).filter_by(session_id=data['session_id']).first()
            if not session:
                session = Session(session_id=data['session_id'])
                self.db.add(session)
                self.db.commit()
                self.db.refresh(session)
            
            # Process each segment
            for segment_data in data['segments']:
                # Ensure speaker exists
                speaker = self.db.query(Speaker).filter_by(
                    speaker_id=segment_data['speaker_id'],
                    speaker_name=segment_data['speaker']
                ).first()
                
                if not speaker:
                    speaker = Speaker(
                        speaker_id=segment_data['speaker_id'],
                        speaker_name=segment_data['speaker'],
                        is_user=bool(segment_data['is_user'])
                    )
                    self.db.add(speaker)
                    self.db.commit()
                    self.db.refresh(speaker)
                
                # Store the segment
                segment = Segment(
                    session_id=session.id,
                    speaker_id=speaker.id,
                    text=segment_data['text'],
                    start_time=datetime.fromisoformat(segment_data['start']),
                    end_time=datetime.fromisoformat(segment_data['end']),
                    log_timestamp=datetime.fromisoformat(data['log_timestamp'])
                )
                self.db.add(segment)
            
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise e

    def get_segments_in_timeframe(self, start_time: str, end_time: str) -> List[Dict[str, Any]]:
        """Retrieve segments within a specific timeframe"""
        try:
            segments = self.db.query(Segment).join(Speaker).filter(
                Segment.log_timestamp.between(start_time, end_time)
            ).order_by(Segment.log_timestamp).all()
            
            return [{
                'text': seg.text,
                'speaker_name': seg.speaker.speaker_name,
                'start_time': seg.start_time.isoformat(),
                'end_time': seg.end_time.isoformat(),
                'log_timestamp': seg.log_timestamp.isoformat()
            } for seg in segments]
        except Exception as e:
            self.db.rollback()
            raise e

    def get_pending_sessions(self) -> List[tuple]:
        """Get sessions that have unprocessed segments"""
        try:
            # Get all processed segment IDs
            processed_ids = set()
            for refined in self.db.query(RefinedSegment).filter(RefinedSegment.source_segments.isnot(None)).all():
                try:
                    ids = json.loads(refined.source_segments)
                    processed_ids.update(ids)
                except json.JSONDecodeError:
                    continue

            # Get sessions with unprocessed segments
            sessions = self.db.query(Session).join(Segment).filter(
                ~Segment.id.in_(processed_ids)
            ).distinct().all()

            return [(session.session_id, session.id) for session in sessions]
        except Exception as e:
            self.db.rollback()
            raise e

    def get_unprocessed_segments(self, session_id: int, limit: int = None) -> List[Dict[str, Any]]:
        """Get unprocessed segments for a session"""
        try:
            query = self.db.query(Segment).filter_by(session_id=session_id)
            if limit:
                query = query.limit(limit)
            return query.all()
        except Exception as e:
            self.db.rollback()
            raise e

    def create_refined_segment(self, session_id: int, segments: List[Dict[str, Any]], 
                             speaker_mapping: Dict[str, str], confidence: float) -> None:
        """Create a refined segment from multiple source segments"""
        try:
            # Get the session
            session = self.db.query(Session).get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            # Create the refined segment
            refined = RefinedSegment(
                session_id=session_id,
                refined_speaker_id=speaker_mapping.get(segments[0]['speaker_id']),
                text=segments[0]['text'],  # Use first segment's text as base
                source_segments=json.dumps([seg['id'] for seg in segments]),
                confidence_score=confidence,
                metadata={
                    'speaker_mapping': speaker_mapping,
                    'source_count': len(segments),
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            self.db.add(refined)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def create_draft_refined_segment(self, session_id: int, segment: Dict[str, Any]) -> None:
        """Create a draft refined segment from a single source segment"""
        try:
            refined = RefinedSegment(
                session_id=session_id,
                refined_speaker_id=segment['speaker_id'],
                text=segment['text'],
                source_segments=json.dumps([segment['id']]),
                confidence_score=0.0,
                metadata={
                    'is_draft': True,
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            self.db.add(refined)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def check_and_lock_segments(self, session_id: int) -> None:
        """Check if any refined segments should be locked"""
        try:
            # Get segments that haven't been updated in a while and aren't locked
            segments = self.db.query(RefinedSegment).filter(
                RefinedSegment.session_id == session_id,
                RefinedSegment.is_locked == False,
                RefinedSegment.last_updated < datetime.utcnow() - timedelta(seconds=10),
                RefinedSegment.confidence_score >= 0.7
            ).all()

            for segment in segments:
                source_count = len(json.loads(segment.source_segments))
                if source_count >= 2:
                    segment.is_locked = True
                    segment.metadata = {
                        **segment.metadata,
                        'locked_at': datetime.utcnow().isoformat()
                    }
                    self.db.commit()
                    self.refine_locked_segment(segment.id, segment.text, session_id)
        except Exception as e:
            self.db.rollback()
            raise e

    def refine_locked_segment(self, segment_id: int, text: str, session_id: int) -> None:
        """Refine a single locked segment's content for clarity"""
        try:
            # Get surrounding context from other locked segments
            context_segments = self.db.query(RefinedSegment).filter(
                RefinedSegment.session_id == session_id,
                RefinedSegment.id != segment_id,
                RefinedSegment.is_locked == True
            ).order_by(RefinedSegment.start_time).all()

            context = [seg.text for seg in context_segments]

            # Call OpenAI for refinement
            prompt = f"""Refine this transcript segment to improve clarity and readability.
Rules:
1. DO NOT change the substantive meaning
2. Fix sentence fragments and grammatical errors
3. Maintain consistent terminology
4. Use context to clarify ambiguous references
5. Preserve speaker-specific language patterns and style
6. Keep technical terms and proper nouns unchanged
7. Maintain informal speech patterns if present

Context (if available):
{chr(10).join(context) if context else "No context available"}

Segment to refine:
{text}

Return ONLY the refined text, with no additional explanation or formatting."""

            try:
                refined_text = call_openai_text(prompt, max_tokens=500)
                
                # Update the segment with refined text
                segment = self.db.query(RefinedSegment).get(segment_id)
                segment.text = refined_text
                segment.metadata = {
                    **segment.metadata,
                    'content_refined': True,
                    'original_text': text,
                    'refined_at': datetime.utcnow().isoformat()
                }
                self.db.commit()
                
                logger.info(f"Refined content for segment {segment_id}")
            except Exception as e:
                logger.error(f"Error refining content for segment {segment_id}: {e}")
                # On error, mark as attempted but failed
                segment = self.db.query(RefinedSegment).get(segment_id)
                segment.metadata = {
                    **segment.metadata,
                    'content_refinement_error': str(e),
                    'refinement_attempted_at': datetime.utcnow().isoformat()
                }
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def cleanup(self):
        """Cleanup database connections"""
        self.db.close() 