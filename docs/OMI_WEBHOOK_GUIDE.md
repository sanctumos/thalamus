# Omi Webhook Integration Guide

## Overview

This guide explains how to integrate and work with Omi webhooks in the Thalamus system. The Omi webhook provides a real-time interface for receiving speech-to-text data that can be processed by the Thalamus transcript refinement system.

## Current Implementation

### Basic Webhook Server (`omi_webhook.py`)

The current implementation provides a simple Flask-based webhook server with two endpoints:

```python
from flask import Flask, request

app = Flask(__name__)

@app.route("/omi", methods=["POST"])
def omi_webhook():
    print(f"🔎 Incoming POST: {request.method} {request.url}")
    try:
        data = request.get_json(force=True)
        print("\n🔥 Cerebellum Input [UNRESTRICTED]:")
        print(data)
        return "OK", 200
    except Exception as e:
        print(f"💥 Failed to parse incoming data: {e}")
        return "Bad Request", 400

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200
```

## Webhook Endpoints

### 1. `/omi` (POST)
- **Purpose**: Receives speech-to-text data from Omi
- **Method**: POST
- **Content-Type**: application/json
- **Response**: "OK" (200) or "Bad Request" (400)

### 2. `/ping` (GET)
- **Purpose**: Health check endpoint
- **Method**: GET
- **Response**: "pong" (200)

## Expected Data Format

The webhook expects JSON data in the following format:

```json
{
    "session_id": "unique_session_identifier",
    "log_timestamp": "2025-03-26T22:48:11.021743Z",
    "segments": [
        {
            "text": "Hello, this is a test.",
            "speaker": "SPEAKER_0",
            "speaker_id": 0,
            "is_user": false,
            "person_id": null,
            "start": 0.0,
            "end": 2.74
        }
    ]
}
```

### Field Descriptions

- **session_id**: Unique identifier for the conversation session
- **log_timestamp**: ISO 8601 timestamp of when the data was generated
- **segments**: Array of speech segments
  - **text**: The transcribed text
  - **speaker**: Speaker identifier (e.g., "SPEAKER_0")
  - **speaker_id**: Numeric speaker ID
  - **is_user**: Boolean indicating if this is the user speaking
  - **person_id**: Optional person identifier
  - **start**: Start time in seconds
  - **end**: End time in seconds

## Integration with Thalamus

### Current Status
The current webhook implementation only logs incoming data. To fully integrate with Thalamus, you need to:

1. **Process the incoming data** using the existing `process_event()` function
2. **Store segments** in the database
3. **Trigger refinement** processing

### Enhanced Integration Example

Here's how to enhance the webhook to integrate with Thalamus:

```python
from flask import Flask, request, jsonify
from database import get_or_create_session, get_or_create_speaker, insert_segment
from datetime import datetime
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/omi", methods=["POST"])
def omi_webhook():
    """Enhanced Omi webhook with Thalamus integration."""
    try:
        data = request.get_json(force=True)
        logger.info(f"Received webhook data for session: {data.get('session_id')}")
        
        # Process the event using existing Thalamus logic
        process_webhook_event(data)
        
        return jsonify({
            "status": "success",
            "message": "Data processed successfully",
            "session_id": data.get('session_id')
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

def process_webhook_event(event):
    """Process webhook event and store in database."""
    try:
        # Parse timestamp
        current_timestamp = datetime.fromisoformat(
            event['log_timestamp'].replace('Z', '+00:00')
        )
        
        # Get or create session
        session_id = event['session_id']
        db_session_id = get_or_create_session(session_id)
        
        # Process each segment
        for segment in event['segments']:
            # Get or create speaker
            speaker_id = int(segment['speaker_id'])
            db_speaker_id = get_or_create_speaker(
                speaker_id=speaker_id,
                speaker_name=segment['speaker'],
                is_user=segment.get('is_user', False)
            )
            
            # Insert segment
            segment_id = insert_segment(
                session_id=db_session_id,
                speaker_id=db_speaker_id,
                text=segment['text'],
                start_time=segment['start'],
                end_time=segment['end'],
                log_timestamp=current_timestamp
            )
            
            logger.info(f"Processed segment {segment_id}: {segment['text'][:50]}...")
            
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")
        raise

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
```

## Running the Webhook Server

### 1. Start the Webhook Server
```bash
python omi_webhook.py
```

The server will start on `http://localhost:5000`

### 2. Test the Webhook
```bash
# Test ping endpoint
curl http://localhost:5000/ping

# Test webhook with sample data
curl -X POST http://localhost:5000/omi \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session_123",
    "log_timestamp": "2025-01-01T12:00:00Z",
    "segments": [
      {
        "text": "Hello, this is a test.",
        "speaker": "SPEAKER_0",
        "speaker_id": 0,
        "is_user": false,
        "person_id": null,
        "start": 0.0,
        "end": 2.5
      }
    ]
  }'
```

## Production Deployment

### 1. Using Gunicorn (Recommended)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 omi_webhook:app
```

### 2. Using systemd Service
Create `/etc/systemd/system/omi-webhook.service`:

```ini
[Unit]
Description=Omi Webhook Service
After=network.target

[Service]
Type=simple
User=thalamus
WorkingDirectory=/opt/thalamus
Environment=PATH=/opt/thalamus/venv/bin
ExecStart=/opt/thalamus/venv/bin/python omi_webhook.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable omi-webhook
sudo systemctl start omi-webhook
```

### 3. Using Docker
Create `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "omi_webhook.py"]
```

Build and run:
```bash
docker build -t omi-webhook .
docker run -p 5000:5000 omi-webhook
```

## Security Considerations

### 1. Authentication
Add API key authentication:

```python
from functools import wraps
import os

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != os.getenv('OMI_API_KEY'):
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route("/omi", methods=["POST"])
@require_api_key
def omi_webhook():
    # ... existing code
```

### 2. Rate Limiting
Implement rate limiting:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route("/omi", methods=["POST"])
@limiter.limit("10 per minute")
def omi_webhook():
    # ... existing code
```

### 3. Input Validation
Add comprehensive input validation:

```python
def validate_webhook_data(data):
    """Validate incoming webhook data."""
    required_fields = ['session_id', 'log_timestamp', 'segments']
    
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    if not isinstance(data['segments'], list):
        raise ValueError("Segments must be a list")
    
    for segment in data['segments']:
        segment_fields = ['text', 'speaker', 'speaker_id', 'start', 'end']
        for field in segment_fields:
            if field not in segment:
                raise ValueError(f"Missing required segment field: {field}")
    
    return True
```

## Monitoring and Logging

### 1. Enhanced Logging
```python
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('omi_webhook.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@app.route("/omi", methods=["POST"])
def omi_webhook():
    start_time = datetime.now()
    try:
        data = request.get_json(force=True)
        logger.info(f"Processing webhook for session: {data.get('session_id')}")
        
        # Process data
        process_webhook_event(data)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Webhook processed successfully in {processing_time:.2f}s")
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
```

### 2. Health Monitoring
```python
@app.route("/health", methods=["GET"])
def health_check():
    """Comprehensive health check."""
    try:
        # Check database connection
        from database import get_db
        with get_db() as conn:
            conn.execute("SELECT 1")
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected"
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500
```

## Error Handling

### 1. Graceful Error Handling
```python
@app.errorhandler(400)
def bad_request(error):
    return jsonify({
        "status": "error",
        "message": "Bad request",
        "error_code": "BAD_REQUEST"
    }), 400

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Internal server error",
        "error_code": "INTERNAL_ERROR"
    }), 500
```

### 2. Retry Logic
```python
import time
from functools import wraps

def retry_on_failure(max_retries=3, delay=1):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

@retry_on_failure(max_retries=3, delay=1)
def process_webhook_event(event):
    # ... existing code
```

## Testing

### 1. Unit Tests
```python
import unittest
from unittest.mock import patch, MagicMock
import json

class TestOmiWebhook(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
    
    def test_ping_endpoint(self):
        response = self.app.get('/ping')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), 'pong')
    
    def test_webhook_valid_data(self):
        test_data = {
            "session_id": "test_session",
            "log_timestamp": "2025-01-01T12:00:00Z",
            "segments": [
                {
                    "text": "Test message",
                    "speaker": "SPEAKER_0",
                    "speaker_id": 0,
                    "is_user": False,
                    "start": 0.0,
                    "end": 2.0
                }
            ]
        }
        
        with patch('omi_webhook.process_webhook_event') as mock_process:
            response = self.app.post('/omi', 
                                   data=json.dumps(test_data),
                                   content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            mock_process.assert_called_once_with(test_data)
    
    def test_webhook_invalid_data(self):
        invalid_data = {"invalid": "data"}
        
        response = self.app.post('/omi',
                               data=json.dumps(invalid_data),
                               content_type='application/json')
        
        self.assertEqual(response.status_code, 400)

if __name__ == '__main__':
    unittest.main()
```

### 2. Load Testing
```python
import requests
import time
import threading

def send_webhook_request():
    data = {
        "session_id": f"test_session_{time.time()}",
        "log_timestamp": "2025-01-01T12:00:00Z",
        "segments": [
            {
                "text": "Load test message",
                "speaker": "SPEAKER_0",
                "speaker_id": 0,
                "is_user": False,
                "start": 0.0,
                "end": 2.0
            }
        ]
    }
    
    response = requests.post('http://localhost:5000/omi', json=data)
    return response.status_code

def run_load_test(num_requests=100, num_threads=10):
    """Run load test with multiple threads."""
    results = []
    
    def worker():
        for _ in range(num_requests // num_threads):
            result = send_webhook_request()
            results.append(result)
    
    threads = []
    for _ in range(num_threads):
        thread = threading.Thread(target=worker)
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    success_rate = sum(1 for r in results if r == 200) / len(results)
    print(f"Success rate: {success_rate:.2%}")

# Run load test
run_load_test()
```

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Find process using port 5000
   netstat -ano | findstr :5000
   
   # Kill process
   taskkill /PID <PID> /F
   ```

2. **Database Connection Issues**
   ```bash
   # Check database file permissions
   ls -la thalamus.db
   
   # Test database connection
   python -c "from database import get_db; print('DB OK')"
   ```

3. **JSON Parsing Errors**
   - Verify Content-Type header is `application/json`
   - Check JSON syntax validity
   - Ensure all required fields are present

### Debug Mode
```python
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
```

## Best Practices

1. **Always validate input data** before processing
2. **Implement proper error handling** and logging
3. **Use HTTPS in production** for security
4. **Implement rate limiting** to prevent abuse
5. **Monitor webhook performance** and set up alerts
6. **Use async processing** for heavy operations
7. **Implement proper authentication** and authorization
8. **Keep webhook endpoints simple** and focused
9. **Use proper HTTP status codes** for responses
10. **Document your webhook API** thoroughly

## Integration Checklist

- [ ] Set up webhook server
- [ ] Implement data validation
- [ ] Add error handling
- [ ] Configure logging
- [ ] Set up monitoring
- [ ] Implement authentication
- [ ] Add rate limiting
- [ ] Create unit tests
- [ ] Set up production deployment
- [ ] Configure health checks
- [ ] Document API endpoints
- [ ] Set up alerting

This guide provides a comprehensive foundation for integrating Omi webhooks with the Thalamus system. Follow the steps and best practices outlined here to create a robust, production-ready webhook integration.
