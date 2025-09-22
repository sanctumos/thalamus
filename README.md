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
python examples/init_db.py
```

## Usage

The Thalamus system is organized as a reference architecture with examples in the `examples/` folder. To run the examples, navigate to the examples directory first:

```bash
cd examples
```

1. Initialize the database:
```bash
python init_db.py
```

2. Start the main application:
```bash
python thalamus_app.py
```

3. Start the transcript refiner (in another terminal):
```bash
python transcript_refiner.py
```

4. Start the webhook server (optional, in another terminal):
```bash
python omi_webhook.py
```

## Project Structure

```
thalamus/
├── examples/           # Reference architecture and examples
│   ├── thalamus_app.py        # Main data ingestion application
│   ├── transcript_refiner.py  # AI-powered transcript refinement
│   ├── database.py            # Database management
│   ├── openai_wrapper.py      # OpenAI API integration
│   ├── omi_webhook.py         # Webhook endpoint
│   ├── utils.py               # Utility functions
│   ├── init_db.py             # Database initialization
│   ├── check_db.py            # Database inspection
│   ├── audit_segment_usage.py # Data integrity verification
│   ├── raw_data_log.json      # Sample test data
│   └── requirements.txt       # Dependencies
├── docs/               # Documentation
│   ├── DEMO_GUIDE.md          # Demo instructions
│   ├── OMI_WEBHOOK_GUIDE.md   # Webhook integration guide
│   └── CHANGELOG.md           # Version history
└── README.md           # This file
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