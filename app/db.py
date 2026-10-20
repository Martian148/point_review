import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(os.environ.get("POINT_REVIEW_DB", Path(__file__).resolve().parent.parent / "data" / "point_review.sqlite3"))


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=20, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 20000")
    return db


@contextmanager
def transaction(immediate=False):
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with transaction() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, nickname TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS points (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL, normalized_title TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK(source_type IN ('MANUAL','MARKDOWN')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uk_point_title_active
            ON points(user_id, normalized_title) WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_point_user ON points(user_id);
        CREATE TABLE IF NOT EXISTS point_content_nodes (
            id INTEGER PRIMARY KEY, point_id INTEGER NOT NULL REFERENCES points(id),
            parent_id INTEGER REFERENCES point_content_nodes(id) ON DELETE CASCADE,
            content TEXT NOT NULL, sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_node_point_parent ON point_content_nodes(point_id,parent_id);
        CREATE TABLE IF NOT EXISTS point_review_states (
            point_id INTEGER PRIMARY KEY REFERENCES points(id),
            mastery INTEGER CHECK(mastery BETWEEN 1 AND 5),
            last_reviewed_at TEXT, next_review_at TEXT,
            review_count INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            correct_streak INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_review_next ON point_review_states(next_review_at);
        CREATE INDEX IF NOT EXISTS idx_review_mastery ON point_review_states(mastery);
        CREATE TABLE IF NOT EXISTS review_sessions (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL CHECK(status IN ('GENERATING','READY','IN_PROGRESS','COMPLETED','FAILED','ABANDONED')),
            planned_question_count INTEGER NOT NULL, actual_question_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT, completed_at TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_session_user_created ON review_sessions(user_id,created_at);
        CREATE TABLE IF NOT EXISTS review_questions (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES review_sessions(id),
            point_id INTEGER NOT NULL REFERENCES points(id),
            target_node_id INTEGER REFERENCES point_content_nodes(id) ON DELETE SET NULL,
            question_type TEXT NOT NULL, context_text TEXT NOT NULL,
            prompt_text TEXT NOT NULL, options_json TEXT NOT NULL,
            correct_option TEXT NOT NULL, explanation TEXT NOT NULL,
            sort_order INTEGER NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(session_id,point_id)
        );
        CREATE INDEX IF NOT EXISTS idx_question_session ON review_questions(session_id);
        CREATE TABLE IF NOT EXISTS review_attempts (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES review_sessions(id),
            question_id INTEGER NOT NULL UNIQUE REFERENCES review_questions(id),
            point_id INTEGER NOT NULL REFERENCES points(id),
            selected_option TEXT NOT NULL CHECK(selected_option IN ('A','B','C','D')),
            is_correct INTEGER NOT NULL, response_time_ms INTEGER,
            mastery_before INTEGER, mastery_after INTEGER,
            answered_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_attempt_point_time ON review_attempts(point_id,answered_at);
        """)
        stamp = now()
        db.execute("INSERT OR IGNORE INTO users(id,nickname,created_at,updated_at) VALUES(1,'本地用户',?,?)", (stamp, stamp))
