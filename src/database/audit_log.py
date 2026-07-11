import sqlite3
import os
import logging

DB_PATH = os.path.expanduser("~/.config/facegate/audit.db")

def init_audit_db():
    """
    Initializes the SQLite database schema if not present.
    Performs safe migration to add 'username' column if missing.
    """
    try:
        db_dir = os.path.dirname(DB_PATH)
        os.makedirs(db_dir, exist_ok=True)
        os.chmod(db_dir, 0o700)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    app_identifier TEXT NOT NULL,
                    method TEXT NOT NULL,
                    result TEXT NOT NULL,
                    confidence_score REAL
                )
            """)
            # Check for column existence and perform alter table migration
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(audit_log)")
            columns = [info[1] for info in cursor.fetchall()]
            if "username" not in columns:
                conn.execute("ALTER TABLE audit_log ADD COLUMN username TEXT")
            conn.commit()
    except Exception as e:
        logging.error(f"Failed to initialize audit database: {e}")

def log_auth_attempt(app_identifier: str, method: str, result: str, confidence_score: float = None, username: str = None):
    """
    Logs an authentication attempt and prunes rows beyond the 1000 limit.
    Confidence score and username are nullable.
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO audit_log (app_identifier, method, result, confidence_score, username) VALUES (?, ?, ?, ?, ?)",
                (app_identifier, method, result, confidence_score, username)
            )
            # Prune to keep only the latest 200 entries
            conn.execute("""
                DELETE FROM audit_log 
                WHERE id NOT IN (
                    SELECT id FROM audit_log ORDER BY id DESC LIMIT 200
                )
            """)
            conn.commit()
            os.chmod(DB_PATH, 0o600)
            logging.info(f"Audit Log: {result.upper()} auth for '{app_identifier}' via {method} (User: {username or 'unknown'}).")
    except Exception as e:
        logging.error(f"Error writing to audit log: {e}")

def get_recent_logs(limit: int = 50) -> list:
    """
    Returns the latest N entries from the audit log database.
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp, app_identifier, method, result, confidence_score, username FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "timestamp": row[0],
                    "app_identifier": row[1],
                    "method": row[2],
                    "result": row[3],
                    "confidence_score": row[4],
                    "username": row[5]
                }
                for row in rows
            ]
    except Exception as e:
        logging.error(f"Error reading from audit log: {e}")
        return []
