# Middleware Pipeline (Real-Time Sensory Processing)
# the System name and project name is Thalamus

## Overview (Zero Context)

This Middleware pipeline actively gathers real-time sensory data from external APIs (primarily audio transcripts and image descriptions), evaluates relevance by communicating directly with an AI subsystem named **Cerebellum** via the **Letta API**, and conditionally escalates relevant data to another central AI agent called **Athena** through a Telegram messaging channel.

**Cerebellum** acts as an instinctive filter—it receives unstructured sensory data (plain text or simple image descriptions), evaluates immediate relevance, and returns structured JSON responses.

Middleware itself has no conversational capabilities; it strictly orchestrates structured data flow.

---

## Middleware Responsibilities (Detailed Functions):

### 1. **Real-time Sensory Data Collection (via Omi API)**
- Middleware actively pulls continuous streams from **Omi API endpoints**:
  - Real-time transcription text streams from human speech.
  - Real-time textual summaries/descriptions from wearable camera images.
- Incoming data is raw, unstructured text or short descriptive sentences.

### 2. **Chunking & Data Preparation**
- Middleware continuously buffers raw data into discrete segments based on practical boundaries:
  - **Audio:** chunks segmented every ~10-15 seconds or at natural speech pauses.
  - **Images:** each discrete description from Omi API forms a chunk independently.
- Middleware adds minimal metadata:
  - `chunk_id`: Unique identifier (UUID preferred).
  - `data_type`: "audio" or "image"
  - `timestamp`: ISO 8601 timestamp

- **Chunk Size Constraint:**  
  Total size of each chunk (metadata + raw data) **must remain below ~1500 tokens** to safely fit within Cerebellum’s response token limits (2048 total tokens in+out per interaction).

### 3. **Communicating with Cerebellum via Letta API**
- Middleware calls the Cerebellum subsystem through the **Letta API**, passing raw data chunks without enforcing any structure:
  - Cerebellum is indifferent to data structure; it evaluates purely based on text content.
- Middleware’s Letta API call (pseudo-example, SDK detailed separately):
```json
{
  "chunk_id": "123e4567-e89b-12d3-a456-426614174000",
  "data_type": "audio",
  "timestamp": "2025-03-24T15:20:30Z",
  "content": "Raw transcription text here (unstructured, as provided by Omi API)."
}
```

- Middleware expects structured responses from Cerebellum via Letta API (always JSON):
```json
{
  "relevant": true,
  "confidence": 0.94,
  "reason": "Mentions important contact (e.g., Schlomo)",
  "timestamp": "2025-03-24T15:20:31Z",
  "snippet": "raw text snippet triggering escalation"
}
```

### 4. **JSON Response Handling (DirtyJSON & Cleaning)**
- Cerebellum returns structured JSON, but Middleware must robustly parse JSON using:
  - **dirtyJSON** module to gracefully handle minor formatting deviations.
  - Custom JSON cleaning utilities (we’ll provide separately).

### 5. **Conditional Escalation to Athena (Telegram Bot API)**
- If Cerebellum response includes `"relevant": true`, Middleware formats concise notification for Athena:
```
🚨 **Sensory Escalation**
Timestamp: 2025-03-24 15:20:30 UTC
Confidence: 94%

Reason: Mentions important contact (e.g., Schlomo)

Snippet: "raw text snippet triggering escalation"
```

- Sends directly to Athena’s dedicated Telegram channel via Telegram Bot API (`python-telegram-bot`).

### 6. **Archival Memory Management (Local Database)**
- Middleware stores every Cerebellum interaction (requests/responses) in local SQLite or PostgreSQL database.
- Automatically prunes archival entries older than one week.

---

## Technical Guidelines (Zero Context):

- **Language & Framework:** Python (FastAPI or plain Python async script preferred)
- **Middleware <-> Cerebellum via Letta API:**  
  SDK usage documentation will be provided separately.
- **Cerebellum Interaction Limits:**  
  **Strictly enforced** 2048-token total limit per interaction. (Incoming chunk ~1500 tokens max, leaving ~500 tokens headroom for Cerebellum response JSON.)
- **Middleware JSON handling:**  
  Implement robust parsing with **dirtyJSON** Python module and custom cleaning functions provided.
- **Telegram Communication:**  
  Simple text notifications via official Telegram Bot API, formatted clearly and concisely.
- **Logging & Error Handling:**  
  Structured logging required, graceful handling of transient errors, retries.

---

## Important Constraints Recap (for implementation):

- Cerebellum receives **raw, unstructured text** inputs.
- Cerebellum outputs strictly structured JSON responses.
- Total interaction size (input + output) with Cerebellum capped at **2048 tokens** per call.
- Middleware’s sole purpose: structured data routing (zero conversational logic).