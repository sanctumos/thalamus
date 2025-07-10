# Thalamus Architecture Documentation

## System Architecture Overview

Thalamus is designed as a modular, event-driven system for real-time transcript processing. The architecture follows a pipeline pattern where data flows through multiple stages of processing and refinement.

## Component Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Raw Audio     │───▶│ Speech-to-Text  │───▶│  Raw Segments   │
│   Input         │    │   Service       │    │   (JSON)        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Refined        │◀───│  Transcript     │◀───│  Thalamus       │
│  Transcripts    │    │  Refiner        │    │  App            │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Database      │    │   OpenAI API    │    │   Database      │
│  (Refined)      │    │   (GPT-4)       │    │   (Raw)         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Core Components

### 1. Data Ingestion Layer (`thalamus_app.py`)

**Purpose**: Processes incoming speech-to-text segments and stores them in the database.

**Key Responsibilities**:
- Parse JSON event data from speech-to-text service
- Extract speaker information and segment metadata
- Create or retrieve session and speaker records
- Store raw segments with timing information
- Simulate real-time processing delays

**Data Flow**:
```python
# Event structure
{
    "session_id": "unique_session_id",
    "log_timestamp": "2025-03-26T22:48:11.021743Z",
    "segments": [
        {
            "text": "Hello, testing.",
            "speaker": "SPEAKER_0",
            "speaker_id": 0,
            "is_user": false,
            "start": 0.0,
            "end": 2.74
        }
    ]
}
```

**Processing Logic**:
1. Parse timestamp and convert to datetime
2. Get or create session record
3. For each segment:
   - Get or create speaker record
   - Insert segment with timing data
   - Log processing status

### 2. Transcript Refinement Engine (`transcript_refiner.py`)

**Purpose**: Continuously processes raw segments and produces refined, coherent transcripts.

**Key Responsibilities**:
- Monitor database for unprocessed segments
- Group segments by speaker for context
- Maintain speaker state across sessions
- Call OpenAI API for text refinement
- Handle idle session cleanup
- Track segment usage to prevent duplicates

**State Management**:
```python
session_states = {
    "session_id": {
        "speaker_id": current_speaker,
        "group": [segments_for_current_speaker],
        "last_received": timestamp
    }
}
```

**Processing Algorithm**:
1. Get unrefined segments for all active sessions
2. Sort segments by start time
3. Group consecutive segments by same speaker
4. When speaker changes or timeout occurs:
   - Combine grouped segments
   - Call OpenAI for refinement
   - Store refined segment
   - Mark raw segments as used

### 3. Database Layer (`database.py`)

**Purpose**: Provides persistent storage and data management for all system components.

**Database Design**:
- **SQLite** for simplicity and portability
- **Connection pooling** with context managers
- **Custom functions** for JSON array operations
- **Foreign key relationships** for data integrity

**Key Functions**:
- `get_or_create_session()` - Session management
- `get_or_create_speaker()` - Speaker management
- `insert_segment()` - Raw segment storage
- `get_unrefined_segments()` - Query unprocessed data
- `insert_refined_segment()` - Store refined content
- `get_used_segment_ids()` - Track processed segments

**Custom SQL Functions**:
```sql
-- JSON array contains function for segment tracking
json_array_contains(arr_str, value)
```

### 4. AI Integration Layer (`openai_wrapper.py`)

**Purpose**: Provides interface to OpenAI API for text refinement.

**Configuration**:
- **Model**: GPT-4
- **Temperature**: 0.7 (balanced creativity/consistency)
- **Max Tokens**: 100 (suitable for segment refinement)
- **Response Format**: JSON

**Error Handling**:
- API rate limiting
- Network timeouts
- Invalid responses
- Authentication failures

## Data Models

### Session Model
```python
{
    "id": int,           # Database primary key
    "session_id": str,   # External session identifier
    "created_at": datetime
}
```

### Speaker Model
```python
{
    "id": int,           # Database primary key
    "name": str,         # Speaker display name
    "created_at": datetime
}
```

### Raw Segment Model
```python
{
    "id": int,           # Database primary key
    "session_id": str,   # Session reference
    "speaker_id": int,   # Speaker foreign key
    "text": str,         # Raw transcript text
    "start_time": float, # Audio start time (seconds)
    "end_time": float,   # Audio end time (seconds)
    "timestamp": datetime # Processing timestamp
}
```

### Refined Segment Model
```python
{
    "id": int,                    # Database primary key
    "session_id": str,            # Session reference
    "refined_speaker_id": int,    # Speaker foreign key
    "text": str,                  # Refined transcript text
    "start_time": float,          # Combined start time
    "end_time": float,            # Combined end time
    "confidence_score": float,    # AI confidence (0-1)
    "source_segments": str,       # JSON array of raw segment IDs
    "metadata": str,              # Additional data (JSON)
    "is_processing": int,         # Processing flag (0/1)
    "last_update": datetime       # Last modification time
}
```

## Processing Pipeline

### Stage 1: Data Ingestion
1. **Event Reception**: Receive JSON events from speech-to-text service
2. **Validation**: Verify event structure and required fields
3. **Session Management**: Create or retrieve session record
4. **Speaker Management**: Create or retrieve speaker records
5. **Segment Storage**: Store raw segments with timing data

### Stage 2: Segment Processing
1. **Query Unprocessed**: Find segments not yet refined
2. **Group by Speaker**: Combine consecutive segments from same speaker
3. **Context Building**: Maintain speaker state across time
4. **Timeout Handling**: Process incomplete groups after inactivity

### Stage 3: AI Refinement
1. **Text Combination**: Merge grouped segments into coherent text
2. **API Call**: Send to OpenAI for enhancement
3. **Response Processing**: Parse and validate AI response
4. **Quality Scoring**: Assign confidence scores

### Stage 4: Data Persistence
1. **Refined Storage**: Store enhanced segments
2. **Usage Tracking**: Mark raw segments as processed
3. **Relationship Mapping**: Link refined to raw segments
4. **Metadata Storage**: Store processing information

## Concurrency and Performance

### Threading Model
- **Single-threaded** processing for simplicity
- **Event-driven** architecture with polling
- **Stateful** session management
- **Idle cleanup** for resource management

### Performance Considerations
- **Database indexing** on frequently queried fields
- **Batch processing** for multiple segments
- **Connection pooling** for database efficiency
- **Memory management** for large sessions

### Scalability Patterns
- **Horizontal scaling** with multiple instances
- **Database sharding** by session ID
- **Message queues** for async processing
- **Caching layers** for frequently accessed data

## Error Handling and Resilience

### Error Categories
1. **Data Validation Errors**: Invalid JSON, missing fields
2. **Database Errors**: Connection failures, constraint violations
3. **API Errors**: OpenAI rate limits, network issues
4. **Processing Errors**: State corruption, memory issues

### Recovery Strategies
- **Graceful degradation**: Continue processing on partial failures
- **Retry mechanisms**: Exponential backoff for transient errors
- **State recovery**: Rebuild session state from database
- **Data consistency**: Transaction rollback on critical errors

### Monitoring and Alerting
- **Comprehensive logging**: All operations logged with context
- **Error tracking**: Centralized error collection and analysis
- **Performance metrics**: Processing latency and throughput
- **Health checks**: System status monitoring

## Security Considerations

### Data Protection
- **Input sanitization**: Validate all incoming data
- **SQL injection prevention**: Parameterized queries
- **API key security**: Environment variable storage
- **Access control**: Database user permissions

### Privacy Features
- **Data anonymization**: Optional speaker name masking
- **Retention policies**: Configurable data lifecycle
- **Audit trails**: Complete processing history
- **Encryption**: Sensitive data encryption at rest

## Deployment Architecture

### Development Environment
```
┌─────────────────┐
│   Local Files   │
│  (raw_data_log) │
└─────────────────┘
         │
         ▼
┌─────────────────┐    ┌─────────────────┐
│  Thalamus App   │───▶│  SQLite DB      │
└─────────────────┘    └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│ Transcript      │───▶│  OpenAI API     │
│ Refiner         │    │  (External)     │
└─────────────────┘    └─────────────────┘
```

### Production Environment
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Load Balancer  │───▶│  Thalamus Apps  │───▶│  SQLite DB      │
│                 │    │  (Multiple)     │    │  (File-based)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Message Queue  │───▶│  Refiner        │───▶│  Redis Cache    │
│  (RabbitMQ)     │    │  Workers        │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Configuration Management

### Environment Variables
```bash
# Required
OPENAI_API_KEY=your_openai_api_key

# Optional
DATABASE_URL=sqlite:///thalamus.db
LOG_LEVEL=INFO
PROCESSING_TIMEOUT=120
MIN_SEGMENTS_FOR_REFINEMENT=4
```

### Configuration Files
- **Database schema**: Defined in `database.py`
- **Processing parameters**: Configurable in refiner
- **Logging configuration**: Centralized logging setup
- **API settings**: OpenAI client configuration

## Testing Strategy

### Unit Testing
- **Database operations**: CRUD operations testing
- **API integration**: OpenAI wrapper testing
- **Data processing**: Segment grouping and refinement
- **Error handling**: Exception scenarios

### Integration Testing
- **End-to-end flows**: Complete processing pipeline
- **Database consistency**: Data integrity verification
- **Performance testing**: Load and stress testing
- **Error recovery**: Failure scenario testing

### Monitoring and Observability
- **Application metrics**: Processing rates and latencies
- **Database metrics**: Query performance and connection usage
- **API metrics**: OpenAI usage and response times
- **System metrics**: Memory, CPU, and disk usage 