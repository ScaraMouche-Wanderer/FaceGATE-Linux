import sqlite3
import os
import logging

DB_PATH = os.path.expanduser("~/.config/facegate/audit.db")

def init_audit_db():
    """
    Initializes the SQLite database schema if not present.
    """
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
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
            conn.commit()
    except Exception as e:
        logging.error(f"Failed to initialize audit database: {e}")

def log_auth_attempt(app_identifier: str, method: str, result: str, confidence_score: float = None):
    """
    Logs an authentication attempt and prunes rows beyond the 1000 limit.
    Confidence score is nullable and stored as REAL.
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO audit_log (app_identifier, method, result, confidence_score) VALUES (?, ?, ?, ?)",
                (app_identifier, method, result, confidence_score)
            )
            # Prune to keep only the latest 1000 entries
            conn.execute("""
                DELETE FROM audit_log 
                WHERE id NOT IN (
                    SELECT id FROM audit_log ORDER BY id DESC LIMIT 1000
                )
            """)
            conn.commit()
            logging.info(f"Audit Log: {result.upper()} auth for '{app_identifier}' via {method}.")
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
                "SELECT timestamp, app_identifier, method, result, confidence_score FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "timestamp": row[0],
                    "app_identifier": row[1],
                    "method": row[2],
                    "result": row[3],
                    "confidence_score": row[4]
                }
                for row in rows
            ]
    except Exception as e:
        logging.error(f"Error reading from audit log: {e}")
        return []
