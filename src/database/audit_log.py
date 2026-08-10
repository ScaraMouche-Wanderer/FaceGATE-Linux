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

def get_app_usage_stats() -> dict:
    """
    Returns aggregated usage statistics from the audit log for dashboard display.
    Returns dict with keys:
        - total_attempts: int
        - total_success: int
        - total_fail: int
        - success_rate: float (0.0-1.0)
        - per_app: dict of {app_identifier: {success, fail, total, avg_score}}
        - hourly_distribution: list of 24 ints (auth attempts per hour of day)
        - recent_events: list of last 5 auth events
        - methods: dict of {method: count}
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Total counts
            cursor.execute("SELECT COUNT(*) FROM audit_log")
            total = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM audit_log WHERE result = 'success'")
            success = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM audit_log WHERE result = 'fail'")
            fail = cursor.fetchone()[0] or 0
            
            # Per-app breakdown
            cursor.execute("""
                SELECT app_identifier,
                       SUM(CASE WHEN result = 'success' THEN 1 ELSE 0 END) as success_count,
                       SUM(CASE WHEN result = 'fail' THEN 1 ELSE 0 END) as fail_count,
                       COUNT(*) as total_count,
                       AVG(CASE WHEN confidence_score IS NOT NULL THEN confidence_score END) as avg_score
                FROM audit_log
                GROUP BY app_identifier
                ORDER BY total_count DESC
            """)
            per_app = {}
            for row in cursor.fetchall():
                per_app[row[0]] = {
                    "success": row[1],
                    "fail": row[2],
                    "total": row[3],
                    "avg_score": row[4]
                }
            
            # Hourly distribution (auth attempts by hour of day)
            cursor.execute("""
                SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hour, COUNT(*)
                FROM audit_log
                GROUP BY hour
                ORDER BY hour
            """)
            hourly = [0] * 24
            for row in cursor.fetchall():
                if row[0] is not None and 0 <= row[0] < 24:
                    hourly[row[0]] = row[1]
            
            # Recent events (last 5)
            cursor.execute("""
                SELECT timestamp, app_identifier, method, result, confidence_score, username
                FROM audit_log ORDER BY id DESC LIMIT 5
            """)
            recent = [
                {
                    "timestamp": row[0],
                    "app_identifier": row[1],
                    "method": row[2],
                    "result": row[3],
                    "confidence_score": row[4],
                    "username": row[5]
                }
                for row in cursor.fetchall()
            ]
            
            # Method distribution
            cursor.execute("""
                SELECT method, COUNT(*) FROM audit_log GROUP BY method ORDER BY COUNT(*) DESC
            """)
            methods = {row[0]: row[1] for row in cursor.fetchall()}
            
            return {
                "total_attempts": total,
                "total_success": success,
                "total_fail": fail,
                "success_rate": (success / total) if total > 0 else 0.0,
                "per_app": per_app,
                "hourly_distribution": hourly,
                "recent_events": recent,
                "methods": methods
            }
    except Exception as e:
        logging.error(f"Error computing app usage stats: {e}")
        return {
            "total_attempts": 0,
            "total_success": 0,
            "total_fail": 0,
            "success_rate": 0.0,
            "per_app": {},
            "hourly_distribution": [0] * 24,
            "recent_events": [],
            "methods": {}
        }


def verify_audit_log_integrity() -> tuple[bool, int, str]:
    """
    Verifies the cryptographic SHA-256 hash chain of the audit database.

    Returns:
        (is_valid: bool, verified_rows_count: int, error_message: str)
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, app_identifier, method, result, confidence_score, username, prev_hash FROM audit_log ORDER BY id ASC")
            rows = cursor.fetchall()
            
            if not rows:
                return True, 0, "Audit log is empty."

            last_hash = "GENESIS"
            count = 0
            for row in rows:
                row_id, app, method, result, score, username, stored_hash = row
                expected_hash = hashlib.sha256(f"{last_hash}:{app}:{method}:{result}:{score}:{username}".encode('utf-8')).hexdigest()
                
                if stored_hash != expected_hash:
                    return False, count, f"Tampering detected at log entry #{row_id} ('{app}'). Hash chain broken."
                
                last_hash = stored_hash
                count += 1

            return True, count, f"Integrity verified across all {count} log entries."
    except Exception as e:
        return False, 0, f"Error verifying audit log integrity: {e}"


def repair_audit_log_integrity() -> tuple[bool, int, str]:
    """
    Re-calculates and re-seals the cryptographic SHA-256 hash chain for all audit log entries.
    Restores valid chain integrity after test runs, manual edits, or schema migrations.

    Returns:
        (success: bool, repaired_count: int, message: str)
    """
    try:
        init_audit_db()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, app_identifier, method, result, confidence_score, username FROM audit_log ORDER BY id ASC")
            rows = cursor.fetchall()
            
            if not rows:
                return True, 0, "Audit log is empty."

            last_hash = "GENESIS"
            count = 0
            for row in rows:
                row_id, app, method, result, score, username = row
                new_hash = hashlib.sha256(f"{last_hash}:{app}:{method}:{result}:{score}:{username}".encode('utf-8')).hexdigest()
                cursor.execute("UPDATE audit_log SET prev_hash = ? WHERE id = ?", (new_hash, row_id))
                last_hash = new_hash
                count += 1

            conn.commit()
            return True, count, f"Successfully re-sealed cryptographic hash chain across all {count} log entries."
    except Exception as e:
        logging.error(f"Error repairing audit log integrity: {e}")
        return False, 0, f"Error repairing audit log integrity: {e}"

