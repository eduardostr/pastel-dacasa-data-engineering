import json
from pathlib import Path
import sqlite3

from etl.load.files import serial, utcnow


class Audit:
    def __init__(self, root):
        path = Path(root) / "control/audit.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("""CREATE TABLE IF NOT EXISTS attempts(
            attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, mode TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
            duration_seconds REAL, summary_json TEXT, error TEXT)""")
        self.connection.commit()

    def start(self, attempt, run_id, mode):
        self.connection.execute("INSERT INTO attempts(attempt_id,run_id,mode,started_at,status) VALUES(?,?,?,?,?)",
                                (attempt, run_id, mode, utcnow().isoformat(), "RUNNING"))
        self.connection.commit()

    def finish(self, attempt, status, duration, summary=None, error=None):
        self.connection.execute("""UPDATE attempts SET status=?,finished_at=?,duration_seconds=?,
            summary_json=?,error=? WHERE attempt_id=?""",
            (status, utcnow().isoformat(), duration, json.dumps(summary, default=serial) if summary else None, error, attempt))
        self.connection.commit()

    def reconcile(self, manifest):
        self.connection.execute("""UPDATE attempts SET status='COMPLETED',error=NULL,
            finished_at=COALESCE(finished_at,?) WHERE attempt_id=?""",
            (utcnow().isoformat(), manifest["attempt_id"]))
        self.connection.commit()

    def close(self):
        self.connection.close()
