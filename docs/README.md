# Thalamus - Real-Time Transcript Refinement System

## Project Overview

Thalamus is a sophisticated real-time transcript refinement system that processes and enhances speech-to-text output using AI. The system is designed to handle live audio streams, identify speakers, and produce refined, readable transcripts.

## Core Architecture

The system consists of several key components working together:

### 1. Data Ingestion (`thalamus_app.py`)
- Processes incoming speech-to-text segments in real-time
- Handles speaker identification and mapping
- Stores raw segments in SQLite database
- Simulates real-time processing with timestamp-based delays

### 2. Transcript Refinement (`transcript_refiner.py`)
- Continuously processes unrefined segments
- Groups segments by speaker for better context
- Maintains session state for speaker continuity
- Handles idle session cleanup
- Produces refined, coherent transcripts

### 3. Database Layer (`database.py`)
- SQLite-based storage with multiple tables
- Handles sessions, speakers, raw segments, and refined segments
- Provides data integrity and relationship tracking
- Includes custom JSON array functions for segment tracking

### 4. AI Integration (`openai_wrapper.py`)
- OpenAI API integration for text refinement
- Configurable model parameters (GPT-4)
- Error handling and logging
- JSON response formatting

## Data Flow

```
Raw Audio → Speech-to-Text → Raw Segments → Thalamus App → Database
                                                      ↓
Refined Transcripts ← Transcript Refiner ← OpenAI API
```

## Key Features

### Real-Time Processing
- Handles live audio streams with timestamp-based synchronization
- Maintains speaker continuity across segments
- Processes multiple sessions concurrently

### Speaker Management
- Automatic speaker identification and mapping
- Speaker state persistence across sessions
- Support for user vs. non-user speaker classification

### Content Refinement
- AI-powered text enhancement for clarity
- Context-aware processing (groups segments by speaker)
- Confidence scoring for refined content

### Data Integrity
- Comprehensive audit trails
- Segment usage tracking
- Duplicate detection and prevention
- Database consistency checks

## Database Schema

### Tables

1. **sessions** - Session management
   - `id` (PRIMARY KEY)
   - `session_id` (UNIQUE)
   - `created_at`

2. **speakers** - Speaker information
   - `id` (PRIMARY KEY)
   - `name`
   - `created_at`

3. **raw_segments** - Original speech-to-text segments
   - `id` (PRIMARY KEY)
   - `session_id`
   - `speaker_id` (FOREIGN KEY)
   - `text`
   - `start_time`, `end_time`
   - `timestamp`

4. **refined_segments** - AI-enhanced segments
   - `id` (PRIMARY KEY)
   - `session_id`
   - `refined_speaker_id` (FOREIGN KEY)
   - `text`
   - `start_time`, `end_time`
   - `confidence_score`
   - `source_segments` (JSON array of raw segment IDs)
   - `metadata`
   - `is_processing`

5. **segment_usage** - Tracking which raw segments are used
   - `raw_segment_id` (PRIMARY KEY)
   - `refined_segment_id` (FOREIGN KEY)
   - `timestamp`

## Configuration

### Environment Variables
- `OPENAI_API_KEY` - Required for AI text refinement

### Dependencies
- Flask 3.0.0 - Web framework (if web interface is added)
- python-dotenv 1.0.0 - Environment variable management
- openai 1.3.0 - OpenAI API client
- sqlalchemy 2.0.23 - Database ORM
- alembic 1.12.1 - Database migrations

## Usage Patterns

### Development Mode
1. Initialize database: `python init_db.py`
2. Start main app: `python thalamus_app.py`
3. Start refiner: `python transcript_refiner.py`

### Production Mode
- Run components as separate services
- Use process managers for reliability
- Implement proper logging and monitoring

## Monitoring and Debugging

### Audit Tools
- `check_db.py` - Database inspection utility
- `audit_segment_usage.py` - Data integrity verification
- `transcript_refiner.log` - Detailed processing logs

### Key Metrics
- Processing latency
- Segment refinement success rate
- Speaker identification accuracy
- Database performance

## Future Enhancements

### Potential Improvements
1. **Web Interface** - Real-time transcript viewing
2. **Multi-language Support** - Internationalization
3. **Advanced Speaker Diarization** - Better speaker identification
4. **Custom AI Models** - Domain-specific refinement
5. **Real-time Collaboration** - Multi-user editing
6. **Export Formats** - PDF, Word, SRT support

### Scalability Considerations
- Database optimization for large datasets
- Horizontal scaling with message queues
- Caching strategies for frequently accessed data
- Load balancing for multiple instances

## Security Considerations

### Data Protection
- Secure API key management
- Database access controls
- Input validation and sanitization
- Audit logging for compliance

### Privacy
- Speaker data anonymization options
- Secure transcript storage
- Data retention policies
- GDPR compliance features

## Troubleshooting

### Common Issues
1. **OpenAI API Limits** - Rate limiting and quota management
2. **Database Locks** - Concurrent access issues
3. **Memory Usage** - Large session processing
4. **SQLite File Permissions** - Ensure write access to database file

### Debug Commands
```bash
# Check database state
python check_db.py

# Audit segment integrity
python audit_segment_usage.py

# View processing logs
tail -f transcript_refiner.log
```

## Contributing

### Development Setup
1. Clone repository
2. Create virtual environment
3. Install dependencies
4. Set up environment variables
5. Initialize database
6. Run tests

### Code Standards
- Follow PEP 8 style guidelines
- Add comprehensive logging
- Include error handling
- Write unit tests for new features

## License

MIT License - See LICENSE file for details 