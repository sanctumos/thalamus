# Thalamus Usage Examples

## Basic Usage Scenarios

### 1. Simple Transcript Processing

#### Setup and Run
```python
# Initialize the system
from database import init_db
from transcript_refiner import TranscriptRefiner

# Initialize database
init_db()

# Create refiner instance
refiner = TranscriptRefiner(
    min_segments_for_diarization=3,
    inactivity_seconds=60
)

# Start processing
refiner.run()
```

#### Process Single Session
```python
from database import get_or_create_session, get_or_create_speaker, insert_segment

# Create session and speaker
session_id = "meeting_20250101"
db_session_id = get_or_create_session(session_id)
speaker_id = get_or_create_speaker(0, "John Doe", False)

# Insert raw segments
segments = [
    {
        "text": "Hello everyone, welcome to the meeting.",
        "start_time": 0.0,
        "end_time": 3.5
    },
    {
        "text": "Today we'll discuss the quarterly results.",
        "start_time": 4.0,
        "end_time": 7.2
    }
]

for segment in segments:
    insert_segment(
        session_id=db_session_id,
        speaker_id=speaker_id,
        text=segment["text"],
        start_time=segment["start_time"],
        end_time=segment["end_time"],
        log_timestamp=datetime.now()
    )
```

### 2. Multi-Speaker Conversation

#### Handle Multiple Speakers
```python
from database import get_or_create_session, get_or_create_speaker, insert_segment
from datetime import datetime

# Create session
session_id = "team_meeting_20250101"
db_session_id = get_or_create_session(session_id)

# Create speakers
speakers = {
    0: get_or_create_speaker(0, "Alice", False),
    1: get_or_create_speaker(1, "Bob", False),
    2: get_or_create_speaker(2, "Charlie", True)  # User
}

# Conversation data
conversation = [
    {"speaker": 0, "text": "Good morning team.", "start": 0.0, "end": 2.1},
    {"speaker": 1, "text": "Morning Alice.", "start": 2.5, "end": 3.8},
    {"speaker": 0, "text": "Let's start with the agenda.", "start": 4.0, "end": 6.2},
    {"speaker": 2, "text": "I have some questions.", "start": 6.5, "end": 8.1},
    {"speaker": 1, "text": "Go ahead Charlie.", "start": 8.3, "end": 9.0}
]

# Insert segments
for turn in conversation:
    insert_segment(
        session_id=db_session_id,
        speaker_id=speakers[turn["speaker"]],
        text=turn["text"],
        start_time=turn["start"],
        end_time=turn["end"],
        log_timestamp=datetime.now()
    )
```

### 3. Real-Time Processing Simulation

#### Simulate Live Audio Stream
```python
import json
import time
from datetime import datetime
from database import get_or_create_session, get_or_create_speaker, insert_segment

def simulate_live_stream():
    """Simulate real-time speech-to-text stream processing."""
    
    # Sample live data
    live_events = [
        {
            "session_id": "live_session_001",
            "timestamp": "2025-01-01T10:00:00Z",
            "segments": [
                {"speaker": "SPEAKER_0", "speaker_id": 0, "text": "Testing", "start": 0.0, "end": 1.0}
            ]
        },
        {
            "session_id": "live_session_001", 
            "timestamp": "2025-01-01T10:00:05Z",
            "segments": [
                {"speaker": "SPEAKER_0", "speaker_id": 0, "text": "one two three", "start": 5.0, "end": 7.0}
            ]
        },
        {
            "session_id": "live_session_001",
            "timestamp": "2025-01-01T10:00:10Z", 
            "segments": [
                {"speaker": "SPEAKER_1", "speaker_id": 1, "text": "Hello there", "start": 10.0, "end": 12.0}
            ]
        }
    ]
    
    # Process events with timing
    for event in live_events:
        # Parse timestamp
        event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        
        # Get or create session
        db_session_id = get_or_create_session(event["session_id"])
        
        # Process segments
        for segment in event["segments"]:
            speaker_id = get_or_create_speaker(
                segment["speaker_id"], 
                segment["speaker"], 
                False
            )
            
            insert_segment(
                session_id=db_session_id,
                speaker_id=speaker_id,
                text=segment["text"],
                start_time=segment["start"],
                end_time=segment["end"],
                log_timestamp=event_time
            )
        
        print(f"Processed event at {event_time}")
        time.sleep(1)  # Simulate real-time delay

# Run simulation
simulate_live_stream()
```

## Advanced Usage Examples

### 1. Custom Transcript Refinement

#### Custom Refinement Logic
```python
from transcript_refiner import TranscriptRefiner
from database import get_unrefined_segments, insert_refined_segment
import json

class CustomTranscriptRefiner(TranscriptRefiner):
    """Custom transcript refiner with specialized processing."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processing_rules = {
            "remove_filler_words": True,
            "fix_grammar": True,
            "add_punctuation": True
        }
    
    def _custom_refine_text(self, text: str, speaker_name: str) -> str:
        """Apply custom refinement rules."""
        refined = text
        
        if self.processing_rules["remove_filler_words"]:
            filler_words = ["um", "uh", "like", "you know", "sort of"]
            for filler in filler_words:
                refined = refined.replace(f" {filler} ", " ")
        
        if self.processing_rules["fix_grammar"]:
            # Basic grammar fixes
            refined = refined.replace(" i ", " I ")
            refined = refined.replace(" i'm ", " I'm ")
        
        if self.processing_rules["add_punctuation"]:
            if not refined.endswith(('.', '!', '?')):
                refined += '.'
        
        return refined
    
    def _finalize_group(self, segments, session_id):
        """Override to use custom refinement."""
        if not segments:
            return
        
        # Get speaker info
        speaker_id = segments[0]['speaker_id']
        speaker_name = segments[0]['speaker_name']
        
        # Combine text
        combined_text = " ".join(s['text'] for s in segments)
        
        # Apply custom refinement
        refined_text = self._custom_refine_text(combined_text, speaker_name)
        
        # Get timing
        start_time = min(s['start_time'] for s in segments)
        end_time = max(s['end_time'] for s in segments)
        
        # Store refined segment
        insert_refined_segment(
            session_id=session_id,
            refined_speaker_id=speaker_id,
            text=refined_text,
            start_time=start_time,
            end_time=end_time,
            source_segments=json.dumps([s['id'] for s in segments]),
            metadata=json.dumps({"custom_refinement": True})
        )

# Usage
custom_refiner = CustomTranscriptRefiner()
custom_refiner.run()
```

### 2. Batch Processing

#### Process Historical Data
```python
import json
from database import get_unrefined_segments, insert_refined_segment
from openai_wrapper import call_openai_text

def batch_process_historical_data():
    """Process all unrefined segments in batches."""
    
    # Get all unrefined segments
    segments = get_unrefined_segments()
    
    if not segments:
        print("No unrefined segments found.")
        return
    
    # Group by session
    sessions = {}
    for segment in segments:
        session_id = segment['session_id']
        if session_id not in sessions:
            sessions[session_id] = []
        sessions[session_id].append(segment)
    
    # Process each session
    for session_id, session_segments in sessions.items():
        print(f"Processing session: {session_id}")
        
        # Group by speaker
        speakers = {}
        for segment in session_segments:
            speaker_id = segment['speaker_id']
            if speaker_id not in speakers:
                speakers[speaker_id] = []
            speakers[speaker_id].append(segment)
        
        # Process each speaker's segments
        for speaker_id, speaker_segments in speakers.items():
            # Sort by time
            speaker_segments.sort(key=lambda x: x['start_time'])
            
            # Combine text
            combined_text = " ".join(s['text'] for s in speaker_segments)
            
            # Call OpenAI for refinement
            try:
                prompt = f"Please refine this transcript for clarity and readability: {combined_text}"
                refined_text = call_openai_text(prompt)
                
                # Store refined segment
                insert_refined_segment(
                    session_id=session_id,
                    refined_speaker_id=speaker_id,
                    text=refined_text,
                    start_time=min(s['start_time'] for s in speaker_segments),
                    end_time=max(s['end_time'] for s in speaker_segments),
                    source_segments=json.dumps([s['id'] for s in speaker_segments]),
                    metadata=json.dumps({"batch_processed": True})
                )
                
                print(f"  Processed {len(speaker_segments)} segments for speaker {speaker_id}")
                
            except Exception as e:
                print(f"  Error processing speaker {speaker_id}: {e}")

# Run batch processing
batch_process_historical_data()
```

### 3. Data Export and Analysis

#### Export Refined Transcripts
```python
import json
import csv
from database import get_refined_segments
from datetime import datetime

def export_transcript_to_csv(session_id: str, output_file: str):
    """Export refined transcript to CSV format."""
    
    # Get refined segments for session
    segments = get_refined_segments(session_id)
    
    if not segments:
        print(f"No refined segments found for session {session_id}")
        return
    
    # Sort by start time
    segments.sort(key=lambda x: x['start_time'])
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'speaker', 'text', 'duration', 'confidence']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        
        for segment in segments:
            duration = segment['end_time'] - segment['start_time']
            
            writer.writerow({
                'timestamp': f"{segment['start_time']:.2f}s",
                'speaker': f"Speaker_{segment['refined_speaker_id']}",
                'text': segment['text'],
                'duration': f"{duration:.2f}s",
                'confidence': f"{segment['confidence_score']:.2f}"
            })
    
    print(f"Exported transcript to {output_file}")

def export_transcript_to_srt(session_id: str, output_file: str):
    """Export refined transcript to SRT subtitle format."""
    
    segments = get_refined_segments(session_id)
    segments.sort(key=lambda x: x['start_time'])
    
    with open(output_file, 'w', encoding='utf-8') as srtfile:
        for i, segment in enumerate(segments, 1):
            # Format timestamps
            start_time = format_timestamp(segment['start_time'])
            end_time = format_timestamp(segment['end_time'])
            
            srtfile.write(f"{i}\n")
            srtfile.write(f"{start_time} --> {end_time}\n")
            srtfile.write(f"Speaker {segment['refined_speaker_id']}: {segment['text']}\n\n")
    
    print(f"Exported SRT to {output_file}")

def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

# Usage examples
export_transcript_to_csv("session_123", "transcript.csv")
export_transcript_to_srt("session_123", "transcript.srt")
```

### 4. Real-Time Monitoring

#### Monitor Processing Status
```python
import time
from database import get_unrefined_segments, get_refined_segments, get_active_sessions

def monitor_processing_status():
    """Monitor real-time processing status."""
    
    print("Thalamus Processing Monitor")
    print("=" * 40)
    
    while True:
        try:
            # Get current status
            unrefined_count = len(get_unrefined_segments())
            refined_count = len(get_refined_segments())
            active_sessions = len(get_active_sessions())
            
            # Calculate processing rate
            current_time = time.time()
            if hasattr(monitor_processing_status, 'last_check'):
                time_diff = current_time - monitor_processing_status.last_check
                if hasattr(monitor_processing_status, 'last_refined_count'):
                    rate = (refined_count - monitor_processing_status.last_refined_count) / time_diff
                else:
                    rate = 0
            else:
                rate = 0
            
            monitor_processing_status.last_check = current_time
            monitor_processing_status.last_refined_count = refined_count
            
            # Display status
            print(f"\r[{time.strftime('%H:%M:%S')}] "
                  f"Unrefined: {unrefined_count:3d} | "
                  f"Refined: {refined_count:3d} | "
                  f"Active Sessions: {active_sessions:2d} | "
                  f"Rate: {rate:.1f} segments/min", end="")
            
            time.sleep(5)  # Update every 5 seconds
            
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(10)

# Start monitoring
monitor_processing_status()
```

### 5. Integration Examples

#### Webhook Integration
```python
from flask import Flask, request, jsonify
from database import get_or_create_session, get_or_create_speaker, insert_segment
from datetime import datetime
import json

app = Flask(__name__)

@app.route('/webhook/transcript', methods=['POST'])
def webhook_transcript():
    """Webhook endpoint for receiving transcript data."""
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['session_id', 'segments']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Process session
        session_id = data['session_id']
        db_session_id = get_or_create_session(session_id)
        
        # Process segments
        processed_count = 0
        for segment_data in data['segments']:
            # Validate segment data
            if not all(k in segment_data for k in ['text', 'speaker', 'speaker_id', 'start', 'end']):
                continue
            
            # Get or create speaker
            speaker_id = get_or_create_speaker(
                segment_data['speaker_id'],
                segment_data['speaker'],
                segment_data.get('is_user', False)
            )
            
            # Insert segment
            insert_segment(
                session_id=db_session_id,
                speaker_id=speaker_id,
                text=segment_data['text'],
                start_time=segment_data['start'],
                end_time=segment_data['end'],
                log_timestamp=datetime.now()
            )
            
            processed_count += 1
        
        return jsonify({
            'status': 'success',
            'processed_segments': processed_count,
            'session_id': session_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcript/<session_id>', methods=['GET'])
def get_transcript(session_id):
    """API endpoint to retrieve refined transcript."""
    
    try:
        from database import get_refined_segments
        
        segments = get_refined_segments(session_id)
        segments.sort(key=lambda x: x['start_time'])
        
        transcript = {
            'session_id': session_id,
            'segments': [
                {
                    'speaker_id': seg['refined_speaker_id'],
                    'text': seg['text'],
                    'start_time': seg['start_time'],
                    'end_time': seg['end_time'],
                    'confidence': seg['confidence_score']
                }
                for seg in segments
            ]
        }
        
        return jsonify(transcript)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

#### Database Migration Example
```python
from database import get_db
import sqlite3

def migrate_database():
    """Example database migration."""
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Add new column to existing table
        try:
            cursor.execute('ALTER TABLE refined_segments ADD COLUMN language TEXT DEFAULT "en"')
            print("Added language column to refined_segments")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("Language column already exists")
            else:
                raise
        
        # Create new index for performance
        try:
            cursor.execute('CREATE INDEX idx_refined_segments_language ON refined_segments(language)')
            print("Created language index")
        except sqlite3.OperationalError as e:
            if "index already exists" in str(e):
                print("Language index already exists")
            else:
                raise
        
        conn.commit()
        print("Migration completed successfully")

# Run migration
migrate_database()
```

## Testing Examples

### Unit Test Example
```python
import unittest
from unittest.mock import patch, MagicMock
from database import get_or_create_session, get_or_create_speaker, insert_segment
from transcript_refiner import TranscriptRefiner

class TestThalamus(unittest.TestCase):
    
    def setUp(self):
        """Set up test database."""
        from database import init_db
        init_db()
    
    def test_session_creation(self):
        """Test session creation and retrieval."""
        session_id = "test_session_001"
        
        # Create session
        db_id_1 = get_or_create_session(session_id)
        self.assertIsInstance(db_id_1, int)
        
        # Retrieve same session
        db_id_2 = get_or_create_session(session_id)
        self.assertEqual(db_id_1, db_id_2)
    
    def test_speaker_management(self):
        """Test speaker creation and retrieval."""
        speaker_id = 1
        speaker_name = "Test Speaker"
        
        # Create speaker
        db_id_1 = get_or_create_speaker(speaker_id, speaker_name)
        self.assertIsInstance(db_id_1, int)
        
        # Retrieve same speaker
        db_id_2 = get_or_create_speaker(speaker_id, speaker_name)
        self.assertEqual(db_id_1, db_id_2)
    
    @patch('openai_wrapper.call_openai_text')
    def test_transcript_refinement(self, mock_openai):
        """Test transcript refinement process."""
        # Mock OpenAI response
        mock_openai.return_value = "Refined transcript text."
        
        # Create test data
        session_id = "test_session_002"
        db_session_id = get_or_create_session(session_id)
        speaker_id = get_or_create_speaker(1, "Test Speaker")
        
        # Insert test segments
        insert_segment(
            session_id=db_session_id,
            speaker_id=speaker_id,
            text="Hello world",
            start_time=0.0,
            end_time=2.0,
            log_timestamp=datetime.now()
        )
        
        # Test refiner
        refiner = TranscriptRefiner(min_segments_for_diarization=1)
        success = refiner.process_session(session_id)
        
        self.assertTrue(success)
        mock_openai.assert_called_once()

if __name__ == '__main__':
    unittest.main()
```

These examples demonstrate various ways to use Thalamus for different scenarios, from basic transcript processing to advanced integrations and custom refinements. 