-- Sessions table to store unique conversation sessions
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Speakers table to store speaker information
CREATE TABLE speakers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    speaker_id INTEGER NOT NULL,
    speaker_name TEXT NOT NULL,
    is_user BOOLEAN DEFAULT FALSE,
    UNIQUE(speaker_id, speaker_name)
);

-- Segments table to store individual speech segments
CREATE TABLE segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    speaker_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    log_timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (speaker_id) REFERENCES speakers(id),
    UNIQUE(session_id, speaker_id, start_time)
);

-- Refined segments table to store processed and diarized data
CREATE TABLE refined_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    refined_speaker_id TEXT NOT NULL,      -- Our determined "true" speaker identifier
    text TEXT NOT NULL,                    -- The refined/combined text
    start_time REAL NOT NULL,              -- Approximate start time
    end_time REAL NOT NULL,                -- Approximate end time
    confidence_score REAL NOT NULL,        -- Confidence in speaker assignment (0-1)
    source_segments TEXT NOT NULL,         -- JSON array of source segment IDs
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_locked BOOLEAN DEFAULT FALSE,       -- Whether this segment's diarization is locked
    metadata JSON,                         -- Additional metadata (e.g., context changes, refinement history)
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    UNIQUE(session_id, refined_speaker_id, start_time)
); 