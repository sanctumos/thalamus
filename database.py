import sqlite3
from datetime import datetime
from contextlib import contextmanager
import json
from typing import List, Dict, Optional
import logging

DB_PATH = 'thalamus.db'
logger = logging.getLogger(__name__)

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
                phase INTEGER DEFAULT 0,
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

def get_unrefined_segments(session_id: Optional[str] = None) -> List[Dict]:
    """Get all unprocessed segments, optionally filtered by session_id."""
    try:
        query = '''
            WITH processed_segments AS (
                SELECT DISTINCT CAST(value AS INTEGER) as segment_id
                FROM refined_segments rs, json_each(rs.source_segments)
                WHERE rs.source_segments IS NOT NULL
                AND rs.confidence_score >= 0.8
                AND json_extract(rs.metadata, '$.is_locked') = 1
            ),
            latest_refined AS (
                SELECT rs.refined_speaker_id, rs.session_id, MAX(rs.id) as latest_id
                FROM refined_segments rs
                GROUP BY rs.refined_speaker_id, rs.session_id
            )
            SELECT s.*, sp.speaker_name 
            FROM segments s
            JOIN speakers sp ON s.speaker_id = sp.id
            LEFT JOIN latest_refined lr ON lr.refined_speaker_id = s.speaker_id AND lr.session_id = s.session_id
            WHERE s.id NOT IN (SELECT segment_id FROM processed_segments)
            AND (lr.latest_id IS NULL OR s.id NOT IN (
                SELECT CAST(value AS INTEGER) as segment_id
                FROM refined_segments rs, json_each(rs.source_segments)
                WHERE rs.id = lr.latest_id
            ))
        '''
        params = []
        if session_id:
            query += ' AND s.session_id = ?'
            params.append(session_id)
        
        query += ' ORDER BY s.start_time'
        
        logger.debug(f"Executing query: {query}")
        logger.debug(f"With params: {params}")
        
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            
            # Convert rows to dicts
            result = [dict(row) for row in rows]
            logger.debug(f"Found {len(result)} unrefined segments")
            return result
            
    except Exception as e:
        logger.error(f"Error getting unrefined segments: {e}")
        logger.exception(e)  # This will print the full stack trace
        return []

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

def get_locked_segments(session_id, limit=None):
    """Get the most recent locked refined segments for a session."""
    with get_db() as conn:
        cur = conn.cursor()
        query = '''
            SELECT * FROM refined_segments 
            WHERE session_id = ? AND is_locked = 1
            ORDER BY start_time DESC
        '''
        if limit:
            query += ' LIMIT ?'
            cur.execute(query, (session_id, limit))
        else:
            cur.execute(query, (session_id,))
        return cur.fetchall() 