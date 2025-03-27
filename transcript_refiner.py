import json
import time
import logging
from datetime import datetime
from database import (
    get_unrefined_segments, insert_refined_segment,
    get_refined_segments
)
from openai_wrapper import call_openai_text
import re
from typing import List, Dict, Optional

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
        logger.info("TranscriptRefiner initialized with min_segments_for_diarization=%d", min_segments_for_diarization)
        
    def get_pending_sessions(self):
        """Get sessions that have unprocessed segments."""
        try:
            logger.debug("Checking for pending sessions...")
            # Get unrefined segments directly - the function now handles filtering
            segments = get_unrefined_segments()
            if not segments:
                logger.debug("No unprocessed segments found")
                return []
            
            # Group by session
            session_counts = {}
            for segment in segments:
                session_counts[segment['session_id']] = session_counts.get(segment['session_id'], 0) + 1

            # Log session counts
            for session_id, count in session_counts.items():
                logger.info("Found session %s with %d unprocessed segments", session_id, count)
            
            return list(session_counts.keys())
                
        except Exception as e:
            logger.error("Error getting pending sessions: %s", e, exc_info=True)
            return []

    def get_unprocessed_segments(self, session_id: str, current_time: datetime) -> List[Dict]:
        """Get segments that need to be processed, up to the current simulation time."""
        try:
            logger.debug("Getting unprocessed segments for session %s up to %s", session_id, current_time)
            # Get segments up to current simulation time
            segments = get_unrefined_segments(session_id)
            
            # Filter segments up to current time
            filtered_segments = [{
                'id': segment['id'],
                'session_id': segment['session_id'],
                'text': segment['text'],
                'speaker_name': segment['speaker_name'],
                'speaker_id': segment['speaker_id'],
                'start_time': float(segment['start_time']),
                'end_time': float(segment['end_time']),
                'log_timestamp': datetime.fromisoformat(segment['log_timestamp'])
            } for segment in segments 
               if datetime.fromisoformat(segment['log_timestamp']) <= current_time]
            
            logger.debug("Found %d unprocessed segments for session %s", len(filtered_segments), session_id)
            return filtered_segments
        except Exception as e:
            logger.error("Error getting unprocessed segments: %s", e, exc_info=True)
            return []

    def process_segment(self, segment: Dict) -> Optional[Dict]:
        """Process a single segment."""
        try:
            logger.debug("Processing segment %d: %s", segment['id'], segment['text'][:50] + "...")
            # Create refined segment directly without diarization
            refined_id = insert_refined_segment(
                session_id=segment['session_id'],
                refined_speaker_id=str(segment['speaker_id']),  # Convert to string
                text=segment['text'],
                start_time=segment['start_time'],
                end_time=segment['end_time'],
                confidence_score=1.0,  # Default confidence for direct mapping
                source_segments=json.dumps([segment['id']]),  # Convert to JSON string
                metadata={  # Convert to JSON string
                    'original_speaker': segment['speaker_name'],
                    'original_speaker_id': segment['speaker_id'],
                    'start_time': float(segment['start_time']),
                    'end_time': float(segment['end_time'])
                }
            )

            if refined_id:
                logger.debug("Successfully created refined segment %d from source segment %d", refined_id, segment['id'])
                return {
                    'id': refined_id,
                    'text': segment['text'],
                    'speaker_id': str(segment['speaker_id']),
                    'confidence': 1.0
                }
            logger.warning("Failed to create refined segment for source segment %d", segment['id'])
            return None
        except Exception as e:
            logger.error("Error processing segment %d: %s", segment['id'], e, exc_info=True)
            return None

    def process_session(self, session_id: str):
        """Process all unprocessed segments for a session."""
        try:
            logger.info("Starting to process session %s", session_id)
            # Get unprocessed segments up to current time
            segments = get_unrefined_segments(session_id)
            if not segments:
                logger.info("No unprocessed segments found for session %s", session_id)
                return
                
            # Get the latest segment's timestamp
            latest_segment = max(segments, key=lambda x: datetime.fromisoformat(x['log_timestamp']))
            current_time = datetime.fromisoformat(latest_segment['log_timestamp'])
            logger.debug("Current processing time: %s", current_time)
            
            # Sort segments by timestamp to process in order
            segments.sort(key=lambda x: (float(x['start_time']), x['id']))
            logger.debug("Found %d segments to process", len(segments))
            
            # Process each segment individually
            processed_count = 0
            for segment in segments:
                try:
                    # Skip if segment timestamp is after current time
                    if datetime.fromisoformat(segment['log_timestamp']) > current_time:
                        logger.debug("Skipping future segment %d (timestamp: %s)", 
                                   segment['id'], segment['log_timestamp'])
                        continue
                        
                    result = self.process_segment(segment)
                    if result:
                        processed_count += 1
                        logger.info("Processed segment %d/%d: %s", 
                                  processed_count, len(segments), segment['text'][:50] + "...")
                    else:
                        logger.error("Failed to process segment %d", segment['id'])
                except Exception as e:
                    logger.error("Error processing segment %d: %s", segment['id'], e, exc_info=True)
                    continue
                
            logger.info("Completed processing session %s: %d/%d segments processed", 
                       session_id, processed_count, len(segments))
            
        except Exception as e:
            logger.error("Error processing session %s: %s", session_id, e, exc_info=True)
            raise

    def run(self):
        """Main processing loop."""
        logger.info("Starting transcript refiner...")
        
        while True:
            try:
                # Get all sessions with unprocessed segments
                pending_sessions = self.get_pending_sessions()
                
                if not pending_sessions:
                    logger.debug("No pending sessions found, waiting...")
                    time.sleep(1)
                    continue
                
                for session_id in pending_sessions:
                    try:
                        self.process_session(session_id)
                    except Exception as e:
                        logger.error("Error processing session %s: %s", session_id, e, exc_info=True)
                        continue
                            
                # Wait before next check
                logger.debug("Waiting 1 second before next check...")
                time.sleep(1)
                
            except Exception as e:
                logger.error("Error in main loop: %s", e, exc_info=True)
                logger.info("Waiting 5 seconds before retrying...")
                time.sleep(5)

if __name__ == '__main__':
    refiner = TranscriptRefiner()
    refiner.run() 