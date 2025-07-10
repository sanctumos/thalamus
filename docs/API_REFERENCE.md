# Thalamus API Reference

## Database API (`database.py`)

### Connection Management

#### `get_db()`
Context manager for database connections with proper timeout and row factory.

**Returns**: Database connection context manager

**Usage**:
```python
with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions")
    results = cursor.fetchall()
```

### Database Initialization

#### `init_db()`
Initializes the database with all required tables and custom functions.

**Creates Tables**:
- `sessions` - Session management
- `speakers` - Speaker information  
- `raw_segments` - Original speech-to-text segments
- `refined_segments` - AI-enhanced segments
- `segment_usage` - Segment processing tracking

**Usage**:
```python
from database import init_db

init_db()
```

### Session Management

#### `get_or_create_session(session_id: str) -> int`
Gets existing session or creates new one.

**Parameters**:
- `session_id` (str): Unique session identifier

**Returns**: Database session ID (int)

**Usage**:
```python
db_session_id = get_or_create_session("unique_session_123")
```

### Speaker Management

#### `get_or_create_speaker(speaker_id: int, speaker_name: str, is_user: bool = False) -> int`
Gets existing speaker or creates new one.

**Parameters**:
- `speaker_id` (int): External speaker identifier
- `speaker_name` (str): Speaker display name
- `is_user` (bool): Whether speaker is the user (default: False)

**Returns**: Database speaker ID (int)

**Usage**:
```python
db_speaker_id = get_or_create_speaker(0, "SPEAKER_0", False)
```

### Raw Segment Operations

#### `insert_segment(session_id: int, speaker_id: int, text: str, start_time: float, end_time: float, log_timestamp: datetime) -> int`
Inserts a new raw segment into the database.

**Parameters**:
- `session_id` (int): Database session ID
- `speaker_id` (int): Database speaker ID
- `text` (str): Raw transcript text
- `start_time` (float): Audio start time in seconds
- `end_time` (float): Audio end time in seconds
- `log_timestamp` (datetime): Processing timestamp

**Returns**: Database segment ID (int)

**Usage**:
```python
segment_id = insert_segment(
    session_id=1,
    speaker_id=2,
    text="Hello, world.",
    start_time=0.0,
    end_time=2.5,
    log_timestamp=datetime.now()
)
```

#### `get_unrefined_segments(session_id: str = None) -> List[Dict]`
Gets all unprocessed raw segments, optionally filtered by session.

**Parameters**:
- `session_id` (str, optional): Filter by specific session

**Returns**: List of segment dictionaries

**Segment Dictionary Structure**:
```python
{
    "id": int,              # Database segment ID
    "session_id": str,      # Session identifier
    "speaker_id": int,      # Database speaker ID
    "text": str,            # Raw transcript text
    "start_time": float,    # Audio start time
    "end_time": float,      # Audio end time
    "timestamp": datetime,  # Processing timestamp
    "speaker_name": str     # Speaker display name
}
```

**Usage**:
```python
# Get all unrefined segments
segments = get_unrefined_segments()

# Get unrefined segments for specific session
segments = get_unrefined_segments("session_123")
```

### Refined Segment Operations

#### `insert_refined_segment(session_id: str, refined_speaker_id: int, text: str, start_time: float, end_time: float, confidence_score: float = 0, source_segments: str = None, metadata: str = None, is_processing: int = 0) -> Optional[int]`
Inserts a new refined segment into the database.

**Parameters**:
- `session_id` (str): Session identifier
- `refined_speaker_id` (int): Database speaker ID
- `text` (str): Refined transcript text
- `start_time` (float): Combined start time
- `end_time` (float): Combined end time
- `confidence_score` (float): AI confidence score (0-1, default: 0)
- `source_segments` (str): JSON array of raw segment IDs (default: None)
- `metadata` (str): Additional metadata as JSON (default: None)
- `is_processing` (int): Processing flag 0/1 (default: 0)

**Returns**: Database refined segment ID (int) or None on error

**Usage**:
```python
refined_id = insert_refined_segment(
    session_id="session_123",
    refined_speaker_id=2,
    text="Hello, world. How are you today?",
    start_time=0.0,
    end_time=5.0,
    confidence_score=0.95,
    source_segments=json.dumps([1, 2, 3]),
    metadata=json.dumps({"model": "gpt-4"})
)
```

#### `get_refined_segments(session_id: str = None) -> List[Dict]`
Gets refined segments, optionally filtered by session.

**Parameters**:
- `session_id` (str, optional): Filter by specific session

**Returns**: List of refined segment dictionaries

**Usage**:
```python
# Get all refined segments
refined = get_refined_segments()

# Get refined segments for specific session
refined = get_refined_segments("session_123")
```

#### `get_refined_segment(segment_id: int) -> Dict`
Gets a specific refined segment by ID.

**Parameters**:
- `segment_id` (int): Database refined segment ID

**Returns**: Refined segment dictionary or None if not found

**Usage**:
```python
segment = get_refined_segment(123)
if segment:
    print(f"Text: {segment['text']}")
    print(f"Confidence: {segment['confidence_score']}")
```

#### `update_refined_segment(segment_id: int, **kwargs) -> bool`
Updates a refined segment with new values.

**Parameters**:
- `segment_id` (int): Database refined segment ID
- `**kwargs`: Fields to update (text, confidence_score, metadata, etc.)

**Returns**: True if successful, False otherwise

**Usage**:
```python
success = update_refined_segment(
    segment_id=123,
    text="Updated transcript text",
    confidence_score=0.98
)
```

### Session Operations

#### `get_active_sessions() -> List[Dict]`
Gets all active sessions with recent activity.

**Returns**: List of session dictionaries

**Usage**:
```python
sessions = get_active_sessions()
for session in sessions:
    print(f"Session: {session['session_id']}")
```

### Segment Usage Tracking

#### `get_used_segment_ids() -> List[int]`
Gets list of raw segment IDs that have been processed.

**Returns**: List of raw segment IDs

**Usage**:
```python
used_ids = get_used_segment_ids()
print(f"Processed {len(used_ids)} segments")
```

#### `get_locked_segments(session_id: str, limit: int = None) -> List[Dict]`
Gets segments currently being processed (locked).

**Parameters**:
- `session_id` (str): Session identifier
- `limit` (int, optional): Maximum number of segments to return

**Returns**: List of locked segment dictionaries

**Usage**:
```python
locked = get_locked_segments("session_123", limit=10)
```

## OpenAI API (`openai_wrapper.py`)

### Text Processing

#### `call_openai_text(prompt: str) -> str`
Calls OpenAI API with text prompt and returns response.

**Parameters**:
- `prompt` (str): Text prompt to send to OpenAI

**Returns**: OpenAI response text

**Configuration**:
- Model: GPT-4
- Temperature: 0.7
- Max Tokens: 100
- Response Format: JSON

**Usage**:
```python
from openai_wrapper import call_openai_text

response = call_openai_text("Please refine this transcript: Hello world.")
print(response)
```

**Error Handling**:
- API rate limiting
- Network timeouts
- Invalid responses
- Authentication failures

## Transcript Refiner API (`transcript_refiner.py`)

### TranscriptRefiner Class

#### `__init__(min_segments_for_diarization: int = 4, inactivity_seconds: int = 120)`
Initializes the transcript refiner.

**Parameters**:
- `min_segments_for_diarization` (int): Minimum segments before processing (default: 4)
- `inactivity_seconds` (int): Timeout for idle sessions (default: 120)

**Usage**:
```python
refiner = TranscriptRefiner(
    min_segments_for_diarization=3,
    inactivity_seconds=60
)
```

#### `process_session(session_id: str) -> bool`
Processes new segments for a specific session.

**Parameters**:
- `session_id` (str): Session identifier to process

**Returns**: True if successful, False on error

**Usage**:
```python
success = refiner.process_session("session_123")
```

#### `flush_idle_sessions()`
Processes any sessions that have been inactive for too long.

**Usage**:
```python
refiner.flush_idle_sessions()
```

#### `run()`
Main processing loop that continuously monitors and processes segments.

**Usage**:
```python
refiner.run()  # Runs indefinitely
```

## Utility Functions (`utils.py`)

### Image Processing

#### `get_image_dimensions(image_path: str) -> Tuple[int, int]`
Returns width and height of an image file.

**Parameters**:
- `image_path` (str): Path to image file

**Returns**: Tuple of (width, height) or None if PIL not available

**Usage**:
```python
dimensions = get_image_dimensions("image.jpg")
if dimensions:
    width, height = dimensions
    print(f"Image size: {width}x{height}")
```

### Prompt Management

#### `load_prompt(filename: str, prompts_dir: str = "./prompts") -> str`
Loads a prompt from a markdown file.

**Parameters**:
- `filename` (str): Name of prompt file
- `prompts_dir` (str): Directory containing prompts (default: "./prompts")

**Returns**: Prompt content as string

**Usage**:
```python
prompt = load_prompt("transcript_refinement.md")
```

### Response Processing

#### `clean_response(response: str, return_dict: bool = False) -> Union[str, Dict]`
Cleans and processes JSON responses safely.

**Parameters**:
- `response` (str): Raw JSON response string
- `return_dict` (bool): Return Python dict if True, JSON string if False

**Returns**: Cleaned JSON string or Python dictionary

**Processing Steps**:
1. Removes markdown code fences
2. Strips whitespace
3. Extracts JSON using regex if standard parsing fails

**Usage**:
```python
# Return cleaned JSON string
clean_json = clean_response(raw_response)

# Return Python dictionary
clean_dict = clean_response(raw_response, return_dict=True)
```

### File Upload

#### `get_image_url(image_input: str) -> str`
Returns URL for image (local file or existing URL).

**Parameters**:
- `image_input` (str): Local file path or URL

**Returns**: Image URL

**Usage**:
```python
url = get_image_url("local_image.jpg")
# Returns uploaded URL or existing URL
```

#### `upload_local_file(file_path: str) -> str`
Uploads local file to temporary hosting service.

**Parameters**:
- `file_path` (str): Path to local file

**Returns**: Uploaded file URL

**Usage**:
```python
url = upload_local_file("document.pdf")
print(f"File available at: {url}")
```

## Audit and Debugging APIs

### Database Inspection (`check_db.py`)

#### `check_db()`
Prints comprehensive database state information.

**Outputs**:
- Sessions table contents
- Speakers table contents
- Raw segments with speaker names
- Refined segments with metadata

**Usage**:
```python
from check_db import check_db

check_db()
```

### Data Integrity (`audit_segment_usage.py`)

#### `audit_segment_integrity()`
Audits segment processing integrity and reports issues.

**Checks**:
- Unrefined segment IDs
- Duplicate raw segment usage
- Segment processing consistency

**Usage**:
```python
from audit_segment_usage import audit_segment_integrity

audit_segment_integrity()
```

## Error Handling

### Common Exceptions

#### Database Errors
```python
try:
    with get_db() as conn:
        # Database operations
except sqlite3.Error as e:
    logger.error(f"Database error: {e}")
```

#### OpenAI API Errors
```python
try:
    response = call_openai_text(prompt)
except Exception as e:
    logger.error(f"OpenAI API error: {e}")
```

#### Processing Errors
```python
try:
    refiner.process_session(session_id)
except Exception as e:
    logger.error(f"Processing error: {e}")
```

## Configuration

### Environment Variables
```bash
# Required
OPENAI_API_KEY=your_openai_api_key

# Optional
DATABASE_URL=sqlite:///thalamus.db
LOG_LEVEL=INFO
```

### Logging Configuration
```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

## Performance Considerations

### Database Optimization
- Use connection pooling with `get_db()` context manager
- Index frequently queried fields
- Use parameterized queries to prevent SQL injection
- Batch operations when possible

### API Rate Limiting
- Implement exponential backoff for OpenAI API calls
- Monitor API usage and quotas
- Cache responses when appropriate

### Memory Management
- Process segments in batches
- Clean up idle session state
- Monitor memory usage for large sessions 