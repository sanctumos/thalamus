# Thalamus

A real-time transcript refinement system that processes and enhances speech-to-text output using AI.

## Features

- Real-time processing of speech-to-text segments
- Speaker identification and mapping
- Content refinement for clarity and readability
- SQLite database for reliable data storage
- Webhook support for event processing

## Prerequisites

- Python 3.8+
- OpenAI API key

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/thalamus.git
cd thalamus
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your OpenAI API key
```

5. Initialize the database:
```bash
python init_db.py
```

## Usage

1. Start the main application:
```bash
python thalamus_app.py
```

2. Start the transcript refiner:
```bash
python transcript_refiner.py
```

3. Start the webhook simulator (optional):
```bash
python replay_webhook_simulator.py
```

## Database Schema

The application uses SQLite with the following tables:

- `sessions`: Stores session information
- `speakers`: Stores speaker information
- `segments`: Stores raw transcript segments
- `refined_segments`: Stores refined transcript segments

## Development

### Running Tests

```bash
python -m pytest tests/
```

## License

MIT License - see LICENSE file for details 