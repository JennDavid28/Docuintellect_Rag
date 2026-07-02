import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "backend/docu_intellect.db")

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 2. Folders Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        parent_id INTEGER,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(parent_id) REFERENCES folders(id) ON DELETE CASCADE
    );
    """)
    
    # 3. Documents Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_path TEXT NOT NULL,
        folder_id INTEGER,
        user_id INTEGER NOT NULL,
        category TEXT,
        summary_short TEXT,
        summary_detailed TEXT,
        summary_pointers TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE SET NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Migration: add graph_cache column for existing databases created before
    # the knowledge graph caching feature. Safe to run every startup — fails
    # silently if the column is already there.
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN graph_cache TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Migration: add transcript_cache column for YouTube documents. Caches the
    # fully-parsed pages (JSON) at upload time so query-time code never has to
    # re-run parse_youtube() — which can fall back to yt-dlp download + local
    # Whisper transcription and take minutes — on every single chat query.
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN transcript_cache TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # 4. Chat Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # 5. Chat Messages Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        role TEXT NOT NULL, -- 'user' or 'assistant'
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
    );
    """)
    
    # 6. Analytics Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        event_type TEXT NOT NULL, -- 'upload', 'query', 'login', etc.
        detail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    conn.commit()
    conn.close()

# --- CRUD Operations ---

# Users
def create_user(username, password_hash, email=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            (username, password_hash, email)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, username, email, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_account(user_id, username=None, email=None, password_hash=None):
    fields = []
    values = []
    if username is not None:
        fields.append("username = ?")
        values.append(username)
    if email is not None:
        fields.append("email = ?")
        values.append(email)
    if password_hash is not None:
        fields.append("password_hash = ?")
        values.append(password_hash)
    if not fields:
        return get_user_by_id(user_id)

    values.append(user_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        if cursor.rowcount == 0:
            return None
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Folders
def create_folder(name, parent_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO folders (name, parent_id, user_id) VALUES (?, ?, ?)",
        (name, parent_id, user_id)
    )
    conn.commit()
    folder_id = cursor.lastrowid
    conn.close()
    return folder_id

def get_folders(user_id):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM folders WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def rename_folder(folder_id, new_name, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE folders SET name = ? WHERE id = ? AND user_id = ?",
        (new_name, folder_id, user_id)
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def delete_folder(folder_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Collect document IDs first so the caller can remove their ES chunks
    docs = cursor.execute(
        "SELECT id, file_path FROM documents WHERE folder_id = ? AND user_id = ?",
        (folder_id, user_id)
    ).fetchall()
    doc_ids = [doc["id"] for doc in docs]
    for doc in docs:
        if os.path.exists(doc["file_path"]):
            try:
                os.remove(doc["file_path"])
            except OSError:
                pass

    cursor.execute("DELETE FROM folders WHERE id = ? AND user_id = ?", (folder_id, user_id))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    # Return (success, doc_ids) so app.py can delete ES chunks for each document
    return success, doc_ids

# Documents
def create_document(filename, file_type, file_path, folder_id, user_id, category=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO documents 
           (filename, file_type, file_path, folder_id, user_id, category) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (filename, file_type, file_path, folder_id, user_id, category)
    )
    conn.commit()
    doc_id = cursor.lastrowid
    conn.close()
    return doc_id

def update_document_summaries(doc_id, short_sum, detailed_sum, pointers_sum):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE documents 
           SET summary_short = ?, summary_detailed = ?, summary_pointers = ? 
           WHERE id = ?""",
        (short_sum, detailed_sum, pointers_sum, doc_id)
    )
    conn.commit()
    conn.close()

def update_document_category(doc_id, category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET category = ? WHERE id = ?", (category, doc_id))
    conn.commit()
    conn.close()

def get_document_graph_cache(doc_id, user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT graph_cache FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchone()
    conn.close()
    return row["graph_cache"] if row and row["graph_cache"] else None

def set_document_graph_cache(doc_id, graph_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET graph_cache = ? WHERE id = ?", (graph_json, doc_id))
    conn.commit()
    conn.close()

def get_document_transcript_cache(doc_id, user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT transcript_cache FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchone()
    conn.close()
    return row["transcript_cache"] if row and row["transcript_cache"] else None

def set_document_transcript_cache(doc_id, pages_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET transcript_cache = ? WHERE id = ?", (pages_json, doc_id))
    conn.commit()
    conn.close()

def get_documents(user_id, folder_id=None):
    conn = get_db_connection()
    if folder_id is not None:
        rows = conn.execute(
            "SELECT * FROM documents WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM documents WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_document_by_id(doc_id, user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def delete_document(doc_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT file_path FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchone()
    if not row:
        conn.close()
        return False
    
    file_path = row["file_path"]
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
            
    cursor.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

# Chat History
def create_chat_session(title, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (title, user_id) VALUES (?, ?)", (title, user_id))
    conn.commit()
    sess_id = cursor.lastrowid
    conn.close()
    return sess_id

def update_chat_session_title(session_id, title):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = ? WHERE id = ? AND title = 'New Chat'", (title, session_id))
    conn.commit()
    conn.close()

def rename_chat_session(session_id, title, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
        (title, session_id, user_id)
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def delete_chat_session(session_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success
    
def get_chat_sessions(user_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_chat_message(session_id, role, content):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    return msg_id

def get_chat_messages(session_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Analytics
def add_analytic_event(user_id, event_type, detail=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO analytics (user_id, event_type, detail) VALUES (?, ?, ?)",
        (user_id, event_type, detail)
    )
    conn.commit()
    conn.close()

def get_analytics_summary(user_id):
    conn = get_db_connection()
    # Doc counts
    doc_count = conn.execute("SELECT COUNT(*) as cnt FROM documents WHERE user_id = ?", (user_id,)).fetchone()["cnt"]
    folder_count = conn.execute("SELECT COUNT(*) as cnt FROM folders WHERE user_id = ?", (user_id,)).fetchone()["cnt"]
    
    # Query counts (event_type = 'query')
    query_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM analytics WHERE user_id = ? AND event_type = 'query'",
        (user_id,)
    ).fetchone()["cnt"]
    
    # Most frequent queries (extracted from detail field)
    rows = conn.execute(
        """SELECT detail, COUNT(detail) as cnt 
           FROM analytics 
           WHERE user_id = ? AND event_type = 'query' AND detail IS NOT NULL
           GROUP BY detail 
           ORDER BY cnt DESC 
           LIMIT 5""",
        (user_id,)
    ).fetchall()
    most_asked = [dict(r) for r in rows]
    
    conn.close()
    return {
        "total_documents": doc_count,
        "total_folders": folder_count,
        "total_queries": query_count,
        "most_asked_queries": most_asked
    }