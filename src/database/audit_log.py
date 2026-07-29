import sqlite3
import os
import logging
import hashlib

DB_PATH = os.path.expanduser("~/.config/facegate/audit.db")

def init_audit_db():
    """
    Initializes the SQLite database schema if not present.
    Performs safe migration to add 'username' and 'prev_hash' columns if missing.
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
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(audit_log)")
            columns = [info[1] for info in cursor.fetchall()]
            if "username" not in columns:
                conn.execute("ALTER TABLE audit_log ADD COLUMN username TEXT")
            if "prev_hash" not in columns:
                conn.execute("ALTER TABLE audit_log ADD COLUMN prev_hash TEXT")
            conn.commit()
    except Exception as e:
        logging.error(f"Failed to initialize audit database: {e}")

def log_auth_attempt(app_identifier: str, method: str, result: str, confidence_score: float = None, username: str = None):
    """
    Logs an authentication attempt with hash chaining and prunes rows beyond 2000 limit.
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT prev_hash, id FROM audit_log ORDER BY id DESC LIMIT 1")
            last_row = cursor.fetchone()
            last_hash = last_row[0] if (last_row and last_row[0]) else "GENESIS"

            # Compute tamper-evident hash of new log entry chained to previous hash
            entry_data = f"{last_hash}:{app_identifier}:{method}:{result}:{confidence_score}:{username}"
            current_hash = hashlib.sha256(entry_data.encode('utf-8')).hexdigest()

            conn.execute(
                "INSERT INTO audit_log (app_identifier, method, result, confidence_score, username, prev_hash) VALUES (?, ?, ?, ?, ?, ?)",
                (app_identifier, method, result, confidence_score, username, current_hash)
            )
            # Prune to keep latest 2000 entries
            conn.execute("""
                DELETE FROM audit_log 
                WHERE id NOT IN (
                    SELECT id FROM audit_log ORDER BY id DESC LIMIT 2000
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
