import sqlite3
from datetime import datetime
from contextlib import contextmanager
import json

DB_PATH = 'thalamus.db'

@contextmanager
def get_db():
    """Get a database connection with proper timeout and row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize database tables."""
    with get_db() as conn:
        cur = conn.cursor()
        
        # Create sessions table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create speakers table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS speakers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                speaker_id INTEGER NOT NULL,
                speaker_name TEXT NOT NULL,
                is_user BOOLEAN DEFAULT 0
            )
        ''')
        
        # Create segments table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                speaker_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                log_timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id),
                FOREIGN KEY (speaker_id) REFERENCES speakers (id)
            )
        ''')
        
        # Create refined_segments table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS refined_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                refined_speaker_id TEXT NOT NULL,
                text TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                confidence_score REAL NOT NULL,
                source_segments TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_locked BOOLEAN DEFAULT 0,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        
        conn.commit()

def get_or_create_session(session_id):
    """Get or create a session and return its ID."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id FROM sessions WHERE session_id = ?', (session_id,))
        result = cur.fetchone()
        
        if result:
            return result['id']
        
        cur.execute('INSERT INTO sessions (session_id) VALUES (?)', (session_id,))
        conn.commit()
        return cur.lastrowid

def get_or_create_speaker(speaker_id, speaker_name, is_user=False):
    """Get or create a speaker and return their ID."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id FROM speakers WHERE speaker_id = ?', (speaker_id,))
        result = cur.fetchone()
        
        if result:
            return result['id']
        
        cur.execute(
            'INSERT INTO speakers (speaker_id, speaker_name, is_user) VALUES (?, ?, ?)',
            (speaker_id, speaker_name, is_user)
        )
        conn.commit()
        return cur.lastrowid

def insert_segment(session_id, speaker_id, text, start_time, end_time, log_timestamp):
    """Insert a new segment."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO segments 
            (session_id, speaker_id, text, start_time, end_time, log_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, speaker_id, text, start_time, end_time, log_timestamp))
        conn.commit()
        return cur.lastrowid

def get_unrefined_segments(session_id=None):
    """Get segments that haven't been refined yet."""
    with get_db() as conn:
        cur = conn.cursor()
        
        # Get all processed segment IDs from refined segments
        cur.execute('SELECT source_segments FROM refined_segments')
        processed_ids = set()
        for row in cur.fetchall():
            try:
                ids = json.loads(row[0])
                processed_ids.update(ids)
            except (json.JSONDecodeError, TypeError):
                continue
        
        # Build the base query
        base_query = '''
            SELECT s.*, sp.speaker_name 
            FROM segments s
            JOIN speakers sp ON s.speaker_id = sp.id
            WHERE s.id NOT IN ({})
        '''
        
        # Handle empty processed_ids case
        if not processed_ids:
            processed_ids = {-1}  # Use dummy ID that won't match anything
            
        placeholders = ','.join('?' * len(processed_ids))
        query = base_query.format(placeholders)
        
        if session_id:
            query += ' AND s.session_id = ?'
            cur.execute(query + ' ORDER BY s.start_time', 
                       tuple(processed_ids) + (session_id,))
        else:
            cur.execute(query + ' ORDER BY s.start_time', 
                       tuple(processed_ids))
            
        return cur.fetchall()

def insert_refined_segment(session_id, refined_speaker_id, text, start_time, end_time,
                         confidence_score, source_segments, metadata=None):
    """Insert a new refined segment."""
    with get_db() as conn:
        cur = conn.cursor()
        metadata_json = json.dumps(metadata) if metadata else None
        cur.execute('''
            INSERT INTO refined_segments 
            (session_id, refined_speaker_id, text, start_time, end_time,
             confidence_score, source_segments, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, refined_speaker_id, text, start_time, end_time,
              confidence_score, source_segments, metadata_json))
        conn.commit()
        return cur.lastrowid

def get_refined_segments(session_id=None):
    """Get refined segments."""
    with get_db() as conn:
        cur = conn.cursor()
        if session_id:
            cur.execute('''
                SELECT * FROM refined_segments 
                WHERE session_id = ?
                ORDER BY start_time
            ''', (session_id,))
        else:
            cur.execute('SELECT * FROM refined_segments ORDER BY start_time')
        return cur.fetchall() 