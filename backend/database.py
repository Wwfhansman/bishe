import sqlite3
import json
import time
import uuid
from typing import List, Dict, Optional

try:
    from .config import env
except Exception:
    def env(name, default=None):
        return default


DB_PATH = env("DB_PATH", "voice_assistant.db")


def _connect(*, row_factory: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def init_db():
    conn = _connect()
    c = conn.cursor()
    # Enable foreign keys
    c.execute("PRAGMA foreign_keys = ON;")
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            wechat_openid TEXT UNIQUE,
            created_at REAL,
            updated_at REAL,
            last_login_at REAL
        )
    ''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_wechat ON users(wechat_openid)")
    
    # Create sessions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at REAL,
            updated_at REAL
        )
    ''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    
    # Create conversations table
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp REAL,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    ''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)")
    
    conn.commit()
    conn.close()

def create_session(user_id: str, title: str = "New Chat") -> str:
    conn = _connect()
    c = conn.cursor()
    
    # Check session count
    c.execute("SELECT id, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at ASC", (user_id,))
    sessions = c.fetchall()
    
    # If limit reached (>=5), delete the oldest
    if len(sessions) >= 5:
        oldest_id = sessions[0][0]
        c.execute("DELETE FROM sessions WHERE id = ?", (oldest_id,))
    
    session_id = str(uuid.uuid4())
    now = time.time()
    c.execute("INSERT INTO sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
              (session_id, user_id, title, now, now))
    
    conn.commit()
    conn.close()
    return session_id

def get_user_sessions(user_id: str) -> List[Dict]:
    conn = _connect(row_factory=True)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_session_history(session_id: str, limit: int = 20) -> List[Dict]:
    conn = _connect(row_factory=True)
    c = conn.cursor()
    c.execute("SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id ASC", (session_id,))
    rows = c.fetchall()
    conn.close()
    # Return last N messages
    return [dict(row) for row in rows][-limit:]


def get_session_owner(session_id: str) -> Optional[str]:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def session_belongs_to(session_id: str, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    owner = get_session_owner(session_id)
    return owner == user_id

def add_message(session_id: str, role: str, content: str):
    conn = _connect()
    c = conn.cursor()
    now = time.time()
    
    # Insert message
    c.execute("INSERT INTO conversations (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (session_id, role, content, now))
    
    # Update session updated_at and title (if it's the first user message and title is default)
    c.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    
    if role == "user":
        # Check if title needs update
        c.execute("SELECT title FROM sessions WHERE id = ?", (session_id,))
        row = c.fetchone()
        if row and row[0] == "New Chat":
            # Use first 20 chars of message as title
            new_title = content[:20] + ("..." if len(content) > 20 else "")
            c.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
            
    conn.commit()
    conn.close()

def clear_history(session_id: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

def delete_session(session_id: str, user_id: Optional[str] = None) -> bool:
    """删除会话及其关联的所有对话记录（级联删除）"""
    conn = _connect()
    c = conn.cursor()
    if user_id:
        c.execute("SELECT id FROM sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    else:
        c.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    c.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return True

def _hash_password(pw: str) -> str:
    import os, hashlib, base64
    salt = os.urandom(16)
    iterations = 120_000
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(h).decode(),
    )

def _verify_password(stored: str, pw: str) -> bool:
    import hashlib, base64
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, iterations_str, salt_b64, hash_b64 = stored.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_b64.encode())
            expected = base64.urlsafe_b64decode(hash_b64.encode())
            actual = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, int(iterations_str))
            return actual == expected
        b = base64.urlsafe_b64decode(stored.encode())
        salt = b[:16]
        h = b[16:]
        return hashlib.sha256(salt + pw.encode()).digest() == h
    except Exception:
        return False

def create_user(username: str, password: str) -> Optional[str]:
    conn = _connect()
    c = conn.cursor()
    now = time.time()
    try:
        user_id = str(uuid.uuid4())
        ph = _hash_password(password)
        c.execute(
            "INSERT INTO users (id, username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, ph, now, now),
        )
        conn.commit()
        return user_id
    except Exception:
        return None
    finally:
        conn.close()

def validate_user(username: str, password: str) -> Optional[str]:
    conn = _connect(row_factory=True)
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    if _verify_password(row["password_hash"], password):
        return row["id"]
    return None

def ensure_user_wechat(openid: str) -> Optional[str]:
    conn = _connect(row_factory=True)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE wechat_openid = ?", (openid,))
    row = c.fetchone()
    if row:
        conn.close()
        return row["id"]
    try:
        uid = str(uuid.uuid4())
        now = time.time()
        c.execute(
            "INSERT INTO users (id, wechat_openid, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (uid, openid, now, now),
        )
        conn.commit()
        return uid
    except Exception:
        return None
    finally:
        conn.close()
