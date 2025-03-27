import json
import time
import logging
from datetime import datetime
from database import (
    get_unrefined_segments, insert_refined_segment,
    get_refined_segments, get_locked_segments, get_db
)
from openai_wrapper import call_openai_text
import re
from typing import List, Dict, Optional, Tuple

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class TranscriptRefiner:
    def __init__(self, min_segments_for_diarization=4):
        self.min_segments = min_segments_for_diarization
        self.sentence_endings = ['.', '!', '?', '...']
        logger.info("TranscriptRefiner initialized with min_segments_for_diarization=%d", min_segments_for_diarization)
        
    def get_pending_sessions(self):
        """Get sessions that have unprocessed segments."""
        try:
            logger.debug("Checking for pending sessions...")
            segments = get_unrefined_segments()
            if not segments:
                logger.debug("No unprocessed segments found")
                return []
            
            session_counts = {}
            for segment in segments:
                session_counts[segment['session_id']] = session_counts.get(segment['session_id'], 0) + 1

            for session_id, count in session_counts.items():
                logger.info("Found session %s with %d unprocessed segments", session_id, count)
            
            return list(session_counts.keys())
                
        except Exception as e:
            logger.error("Error getting pending sessions: %s", e, exc_info=True)
            return []

    def is_complete_sentence(self, text: str) -> bool:
        """Check if text forms a complete sentence."""
        text = text.strip()
        return any(text.endswith(end) for end in self.sentence_endings)

    def calculate_confidence(self, text: str, segments: List[Dict]) -> float:
        """Calculate confidence score based on sentence completeness and segment count."""
        if not text:
            return 0.0
            
        # Base confidence on sentence completeness
        base_confidence = 0.7 if self.is_complete_sentence(text) else 0.3
        
        # Adjust based on number of segments (more segments = higher confidence)
        segment_factor = min(len(segments) / 3, 1.0)  # Cap at 1.0
        
        # Adjust based on text length (longer text = higher confidence)
        length_factor = min(len(text.split()) / 10, 1.0)  # Cap at 1.0
        
        return min(base_confidence + (segment_factor * 0.2) + (length_factor * 0.1), 1.0)

    def combine_segments(self, segments: List[Dict]) -> Tuple[str, float, float]:
        """Combine segments into a single text with proper timing."""
        if not segments:
            return "", 0.0, 0.0
            
        # Sort segments by start time
        segments.sort(key=lambda x: float(x['start_time']))
        
        # Combine text with proper spacing
        text = " ".join(segment['text'].strip() for segment in segments)
        
        # Get start and end times from first and last segments
        start_time = float(segments[0]['start_time'])
        end_time = float(segments[-1]['end_time'])
        
        return text, start_time, end_time

    def phase1_refinement(self, segments: List[Dict]) -> List[Dict]:
        """Phase 1: Combine segments into complete sentences and lock high-confidence ones."""
        refined_segments = []
        current_group = []
        
        # Sort segments by start time
        segments.sort(key=lambda x: float(x['start_time']))
        
        for segment in segments:
            current_group.append(segment)
            raw_text, start_time, end_time = self.combine_segments(current_group)
            
            # If we have a complete sentence or enough segments, process the group
            if self.is_complete_sentence(raw_text) or len(current_group) >= 3:
                # Call OpenAI to combine and refine the text
                prompt = f"""Please combine and refine these transcript segments into proper sentences:

Original text: {raw_text}

Rules:
1. Maintain the original meaning
2. Create complete, grammatically correct sentences
3. Keep speaker's natural speech patterns
4. Do not add new information
5. Combine fragments into complete thoughts
6. Fix any obvious transcription errors

Response format:
Text: [refined text]
Confidence: [0-1 score for how confident you are in the refinement]
Complete: [true/false for whether this forms complete sentence(s)]
Combined: [true/false for whether this combines multiple fragments]"""

                try:
                    response = call_openai_text(prompt)
                    if response:
                        # Parse OpenAI response
                        refined_text = None
                        confidence = 0.0
                        is_complete = False
                        is_combined = False
                        
                        for line in response.split('\n'):
                            if line.startswith('Text:'):
                                refined_text = line[5:].strip()
                            elif line.startswith('Confidence:'):
                                try:
                                    confidence = float(line[11:].strip())
                                except ValueError:
                                    confidence = 0.0
                            elif line.startswith('Complete:'):
                                is_complete = line[9:].strip().lower() == 'true'
                            elif line.startswith('Combined:'):
                                is_combined = line[9:].strip().lower() == 'true'
                        
                        if refined_text:
                            # Create refined segment
                            refined_id = insert_refined_segment(
                                session_id=segment['session_id'],
                                refined_speaker_id=str(segment['speaker_id']),
                                text=refined_text,
                                start_time=start_time,
                                end_time=end_time,
                                confidence_score=confidence,
                                source_segments=json.dumps([s['id'] for s in current_group]),
                                metadata={
                                    'original_speaker': segment['speaker_name'],
                                    'original_speaker_id': segment['speaker_id'],
                                    'start_time': start_time,
                                    'end_time': end_time,
                                    'phase': 1,
                                    'is_locked': confidence >= 0.8 and is_complete,
                                    'is_combined': is_combined
                                }
                            )
                            
                            if refined_id:
                                refined_segments.append({
                                    'id': refined_id,
                                    'text': refined_text,
                                    'speaker_id': str(segment['speaker_id']),
                                    'confidence': confidence,
                                    'is_locked': confidence >= 0.8 and is_complete
                                })
                                
                            current_group = []
                            continue
                except Exception as e:
                    logger.error(f"Error calling OpenAI for refinement: {e}")
                
                # Fallback to basic refinement if OpenAI call fails
                confidence = self.calculate_confidence(raw_text, current_group)
                refined_id = insert_refined_segment(
                    session_id=segment['session_id'],
                    refined_speaker_id=str(segment['speaker_id']),
                    text=raw_text,
                    start_time=start_time,
                    end_time=end_time,
                    confidence_score=confidence,
                    source_segments=json.dumps([s['id'] for s in current_group]),
                    metadata={
                        'original_speaker': segment['speaker_name'],
                        'original_speaker_id': segment['speaker_id'],
                        'start_time': start_time,
                        'end_time': end_time,
                        'phase': 1,
                        'is_locked': confidence >= 0.8,
                        'is_combined': len(current_group) > 1
                    }
                )
                
                if refined_id:
                    refined_segments.append({
                        'id': refined_id,
                        'text': raw_text,
                        'speaker_id': str(segment['speaker_id']),
                        'confidence': confidence,
                        'is_locked': confidence >= 0.8
                    })
                
                current_group = []
        
        # Process any remaining segments
        if current_group:
            raw_text, start_time, end_time = self.combine_segments(current_group)
            
            # Try OpenAI refinement for remaining segments
            prompt = f"""Please combine and refine these transcript segments into proper sentences:

Original text: {raw_text}

Rules:
1. Maintain the original meaning
2. Create complete, grammatically correct sentences
3. Keep speaker's natural speech patterns
4. Do not add new information
5. Combine fragments into complete thoughts
6. Fix any obvious transcription errors

Response format:
Text: [refined text]
Confidence: [0-1 score for how confident you are in the refinement]
Complete: [true/false for whether this forms complete sentence(s)]
Combined: [true/false for whether this combines multiple fragments]"""

            try:
                response = call_openai_text(prompt)
                if response:
                    # Parse OpenAI response
                    refined_text = None
                    confidence = 0.0
                    is_complete = False
                    is_combined = False
                    
                    for line in response.split('\n'):
                        if line.startswith('Text:'):
                            refined_text = line[5:].strip()
                        elif line.startswith('Confidence:'):
                            try:
                                confidence = float(line[11:].strip())
                            except ValueError:
                                confidence = 0.0
                        elif line.startswith('Complete:'):
                            is_complete = line[9:].strip().lower() == 'true'
                        elif line.startswith('Combined:'):
                            is_combined = line[9:].strip().lower() == 'true'
                    
                    if refined_text:
                        refined_id = insert_refined_segment(
                            session_id=segment['session_id'],
                            refined_speaker_id=str(segment['speaker_id']),
                            text=refined_text,
                            start_time=start_time,
                            end_time=end_time,
                            confidence_score=confidence,
                            source_segments=json.dumps([s['id'] for s in current_group]),
                            metadata={
                                'original_speaker': segment['speaker_name'],
                                'original_speaker_id': segment['speaker_id'],
                                'start_time': start_time,
                                'end_time': end_time,
                                'phase': 1,
                                'is_locked': confidence >= 0.8 and is_complete,
                                'is_combined': is_combined
                            }
                        )
                        
                        if refined_id:
                            refined_segments.append({
                                'id': refined_id,
                                'text': refined_text,
                                'speaker_id': str(segment['speaker_id']),
                                'confidence': confidence,
                                'is_locked': confidence >= 0.8 and is_complete
                            })
                        return refined_segments
            except Exception as e:
                logger.error(f"Error calling OpenAI for refinement: {e}")
            
            # Fallback to basic refinement if OpenAI call fails
            confidence = self.calculate_confidence(raw_text, current_group)
            refined_id = insert_refined_segment(
                session_id=segment['session_id'],
                refined_speaker_id=str(segment['speaker_id']),
                text=raw_text,
                start_time=start_time,
                end_time=end_time,
                confidence_score=confidence,
                source_segments=json.dumps([s['id'] for s in current_group]),
                metadata={
                    'original_speaker': segment['speaker_name'],
                    'original_speaker_id': segment['speaker_id'],
                    'start_time': start_time,
                    'end_time': end_time,
                    'phase': 1,
                    'is_locked': confidence >= 0.8,
                    'is_combined': len(current_group) > 1
                }
            )
            
            if refined_id:
                refined_segments.append({
                    'id': refined_id,
                    'text': raw_text,
                    'speaker_id': str(segment['speaker_id']),
                    'confidence': confidence,
                    'is_locked': confidence >= 0.8
                })
        
        return refined_segments

    def phase2_refinement(self, session_id: str):
        """Phase 2: Apply corrections to the last 3 locked segments."""
        try:
            # Get the last 3 locked segments
            locked_segments = get_locked_segments(session_id, limit=3)
            if len(locked_segments) < 3:
                logger.debug("Not enough locked segments for phase 2 refinement")
                return
                
            # Focus on the middle segment
            target_segment = locked_segments[1]
            
            # Prepare context from surrounding segments
            context = f"Previous: {locked_segments[0]['text']}\n"
            context += f"Current: {target_segment['text']}\n"
            context += f"Next: {locked_segments[2]['text']}"
            
            # Call OpenAI for corrections
            prompt = f"""Please correct the following transcript segment, focusing on:
1. Industry-specific terms
2. Numbers and measurements
3. Proper names
4. Punctuation and grammar

Context:
{context}

Please provide only the corrected text, without any explanations."""
            
            corrected_text = call_openai_text(prompt)
            if not corrected_text:
                logger.warning("Failed to get corrections for segment %d", target_segment['id'])
                return
                
            # Create new refined segment with corrections
            refined_id = insert_refined_segment(
                session_id=session_id,
                refined_speaker_id=target_segment['speaker_id'],
                text=corrected_text,
                start_time=target_segment['start_time'],
                end_time=target_segment['end_time'],
                confidence_score=0.9,  # Slightly lower confidence for corrections
                source_segments=json.dumps([target_segment['id']]),
                metadata={
                    'original_speaker': target_segment['speaker_name'],
                    'original_speaker_id': target_segment['speaker_id'],
                    'start_time': target_segment['start_time'],
                    'end_time': target_segment['end_time'],
                    'phase': 2,
                    'is_locked': True,
                    'corrections_applied': True
                }
            )
            
            if refined_id:
                logger.info("Created phase 2 refined segment %d from source segment %d", 
                          refined_id, target_segment['id'])
                
        except Exception as e:
            logger.error("Error in phase 2 refinement: %s", e, exc_info=True)

    def process_session(self, session_id: str):
        """Process all unprocessed segments for a session."""
        try:
            logger.info("Starting to process session %s", session_id)
            segments = get_unrefined_segments(session_id)
            if not segments:
                logger.info("No unprocessed segments found for session %s", session_id)
                return
                
            # Sort segments by timestamp
            segments.sort(key=lambda x: float(x['start_time']))
            
            # First pass: Basic diarization grouping
            current_speaker = None
            current_group = []
            current_text = []
            current_start = None
            current_end = None
            
            for segment in segments:
                speaker_id = segment['speaker_id']
                start_time = float(segment['start_time'])
                end_time = float(segment['end_time'])
                
                # If speaker changes, create a new refined segment
                if current_speaker is not None and current_speaker != speaker_id:
                    # Create refined segment for previous speaker's group
                    refined_id = insert_refined_segment(
                        session_id=session_id,
                        refined_speaker_id=str(current_speaker),
                        text=" ".join(current_text),
                        start_time=current_start,
                        end_time=current_end,
                        confidence_score=0.5,  # Placeholder confidence until Phase 1
                        source_segments=json.dumps([s['id'] for s in current_group]),
                        metadata={
                            'original_speaker': current_group[0]['speaker_name'],
                            'original_speaker_id': current_speaker,
                            'start_time': current_start,
                            'end_time': current_end,
                            'phase': 0,  # Phase 0 indicates basic diarization only
                            'is_locked': False,
                            'is_combined': len(current_group) > 1,
                            'needs_refinement': True
                        }
                    )
                    logger.debug(f"Created basic diarization segment for speaker {current_speaker} with {len(current_group)} raw segments")
                    
                    # Reset for new speaker
                    current_group = []
                    current_text = []
                    current_start = None
                    current_end = None
                
                # Initialize or update current group
                if not current_group:
                    current_start = start_time
                    current_speaker = speaker_id
                
                current_group.append(segment)
                current_text.append(segment['text'].strip())
                current_end = end_time
            
            # Handle last group
            if current_group:
                refined_id = insert_refined_segment(
                    session_id=session_id,
                    refined_speaker_id=str(current_speaker),
                    text=" ".join(current_text),
                    start_time=current_start,
                    end_time=current_end,
                    confidence_score=0.5,  # Placeholder confidence until Phase 1
                    source_segments=json.dumps([s['id'] for s in current_group]),
                    metadata={
                        'original_speaker': current_group[0]['speaker_name'],
                        'original_speaker_id': current_speaker,
                        'start_time': current_start,
                        'end_time': current_end,
                        'phase': 0,  # Phase 0 indicates basic diarization only
                        'is_locked': False,
                        'is_combined': len(current_group) > 1,
                        'needs_refinement': True
                    }
                )
                logger.debug(f"Created basic diarization segment for speaker {current_speaker} with {len(current_group)} raw segments")
            
            # Second pass: Apply Phase 1 refinement to completed diarization groups
            # This will be handled in a separate method call to avoid processing partial groups
            
            logger.info("Completed basic diarization for session %s", session_id)
            
        except Exception as e:
            logger.error("Error processing session %s: %s", session_id, e, exc_info=True)
            raise

    def refine_diarized_segments(self, session_id: str):
        """Apply Phase 1 refinement to completed diarization groups."""
        try:
            # Get all segments that need refinement
            query = '''
                SELECT * FROM refined_segments 
                WHERE session_id = ? AND phase = 0 AND needs_refinement = 1
                ORDER BY start_time
            '''
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(query, (session_id,))
                segments_to_refine = cur.fetchall()
            
            logger.debug(f"Found {len(segments_to_refine)} segments to refine for session {session_id}")
            
            for segment in segments_to_refine:
                # Get metadata - convert Row to dict for JSON serialization
                segment_dict = dict(segment)
                metadata = json.loads(segment_dict['metadata']) if segment_dict['metadata'] else {}
                
                # Check if we should lock based on previous attempts
                should_lock = False
                lock_reason = None
                
                # 1. High confidence and complete
                if metadata.get('confidence', 0) >= 0.8 and metadata.get('is_complete', False):
                    should_lock = True
                    lock_reason = "high_confidence_complete"
                
                # 2. Multiple refinement attempts (3 or more)
                elif metadata.get('refinement_attempts', 0) >= 3:
                    should_lock = True
                    lock_reason = "max_attempts"
                
                # 3. Time elapsed (5 minutes or more)
                elif metadata.get('first_attempt_time'):
                    first_attempt = datetime.fromisoformat(metadata['first_attempt_time'])
                    if (datetime.now() - first_attempt).total_seconds() > 300:  # 5 minutes
                        should_lock = True
                        lock_reason = "time_elapsed"
                
                # Call OpenAI to refine the text
                prompt = f"""Please refine this transcript segment into proper sentences:

Original text: {segment_dict['text']}

Rules:
1. Maintain the original meaning
2. Create complete, grammatically correct sentences
3. Keep speaker's natural speech patterns
4. Do not add new information
5. Fix any obvious transcription errors

Response format:
Text: [refined text]
Confidence: [0-1 score for how confident you are in the refinement]
Complete: [true/false for whether this forms complete sentence(s)]"""

                try:
                    response = call_openai_text(prompt)
                    if response:
                        # Parse OpenAI response
                        refined_text = None
                        confidence = 0.0
                        is_complete = False
                        
                        for line in response.split('\n'):
                            if line.startswith('Text:'):
                                refined_text = line[5:].strip()
                            elif line.startswith('Confidence:'):
                                try:
                                    confidence = float(line[11:].strip())
                                except ValueError:
                                    confidence = 0.0
                            elif line.startswith('Complete:'):
                                is_complete = line[9:].strip().lower() == 'true'
                        
                        if refined_text:
                            # Update metadata
                            metadata.update({
                                'confidence': confidence,
                                'is_complete': is_complete,
                                'refinement_attempts': metadata.get('refinement_attempts', 0) + 1,
                                'last_attempt_time': datetime.now().isoformat(),
                                'lock_reason': lock_reason if should_lock else None,
                                'phase': 1,  # Update to Phase 1
                                'is_locked': should_lock,
                                'needs_refinement': not should_lock  # Only needs refinement if not locked
                            })
                            
                            # Set first attempt time if not set
                            if 'first_attempt_time' not in metadata:
                                metadata['first_attempt_time'] = datetime.now().isoformat()
                            
                            # Create new refined segment with Phase 1 refinement
                            refined_id = insert_refined_segment(
                                session_id=segment_dict['session_id'],
                                refined_speaker_id=segment_dict['refined_speaker_id'],
                                text=refined_text,
                                start_time=segment_dict['start_time'],
                                end_time=segment_dict['end_time'],
                                confidence_score=confidence,
                                source_segments=segment_dict['source_segments'],
                                metadata=metadata
                            )
                            logger.info(f"Created Phase 1 refined segment {refined_id} from diarized segment {segment_dict['id']} (confidence: {confidence:.2f}, complete: {is_complete}, locked: {should_lock})")
                except Exception as e:
                    logger.error(f"Error refining segment {segment_dict['id']}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error refining diarized segments for session {session_id}: {e}")

    def run(self):
        """Main processing loop."""
        logger.info("Starting transcript refiner...")
        
        while True:
            try:
                pending_sessions = self.get_pending_sessions()
                
                if not pending_sessions:
                    logger.debug("No pending sessions found, waiting...")
                    time.sleep(1)
                    continue
                
                for session_id in pending_sessions:
                    try:
                        # First pass: Basic diarization grouping
                        self.process_session(session_id)
                        
                        # Second pass: Apply refinement to completed groups
                        self.refine_diarized_segments(session_id)
                        
                    except Exception as e:
                        logger.error("Error processing session %s: %s", session_id, e, exc_info=True)
                        continue
                            
                logger.debug("Waiting 1 second before next check...")
                time.sleep(1)
                
            except Exception as e:
                logger.error("Error in main loop: %s", e, exc_info=True)
                logger.info("Waiting 5 seconds before retrying...")
                time.sleep(5)

if __name__ == '__main__':
    refiner = TranscriptRefiner()
    refiner.run() 