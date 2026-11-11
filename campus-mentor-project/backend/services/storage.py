"""등록 선배·로그인 토큰·채팅 메시지·대화 종료 상태를 SQLite 파일에 저장한다."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "app.db"
PIN_ITERATIONS = 200_000
TOKEN_DAYS = 30
_lock = threading.Lock()


@contextmanager
def _db():
    with _lock:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def init() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mentors (
                mentor_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL UNIQUE,
                major TEXT NOT NULL,
                status TEXT NOT NULL,
                bio TEXT NOT NULL,
                pin_salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tokens (
                token_hash TEXT PRIMARY KEY,
                mentor_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                room TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_room ON messages (room);
            CREATE TABLE IF NOT EXISTS end_states (
                room TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                requested_by TEXT,
                declined_by TEXT
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PIN_ITERATIONS).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- 등록 선배 ----
def list_mentors() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT mentor_id, display_name, major, status, bio FROM mentors ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def name_taken(display_name: str) -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM mentors WHERE display_name = ?", (display_name,)
        ).fetchone()
    return row is not None


def add_mentor(mentor_id: str, display_name: str, major: str, status: str, bio: str, pin: str) -> None:
    """PIN은 솔트를 붙인 해시로만 저장한다. 닉네임이 겹치면 sqlite3.IntegrityError."""
    salt = secrets.token_hex(16)
    with _db() as conn:
        conn.execute(
            "INSERT INTO mentors VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mentor_id, display_name, major, status, bio, salt, _hash_pin(pin, salt), _now()),
        )


def check_pin(display_name: str, pin: str) -> str | None:
    """닉네임과 PIN이 맞으면 mentor_id, 아니면 None."""
    with _db() as conn:
        row = conn.execute(
            "SELECT mentor_id, pin_salt, pin_hash FROM mentors WHERE display_name = ?",
            (display_name,),
        ).fetchone()
    if row is None:
        return None
    if not hmac.compare_digest(_hash_pin(pin, row["pin_salt"]), row["pin_hash"]):
        return None
    return row["mentor_id"]


# ---- 로그인 토큰 (DB에는 토큰 해시만 저장) ----
def create_token(mentor_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute(
            "INSERT INTO tokens VALUES (?, ?, ?)", (_hash_token(token), mentor_id, _now())
        )
    return token


def token_mentor(token: str) -> str | None:
    if not token:
        return None
    with _db() as conn:
        row = conn.execute(
            "SELECT mentor_id, created_at FROM tokens WHERE token_hash = ?", (_hash_token(token),)
        ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["created_at"]) < datetime.now(timezone.utc) - timedelta(days=TOKEN_DAYS):
        delete_token(token)
        return None
    return row["mentor_id"]


def delete_token(token: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM tokens WHERE token_hash = ?", (_hash_token(token),))


# ---- 채팅 메시지 ----
def add_message(room: str, message: dict) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
            (message["id"], room, message["senderRole"], message["text"], message["createdAt"]),
        )


def list_messages(room: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, sender_role, text, created_at FROM messages WHERE room = ? ORDER BY rowid",
            (room,),
        ).fetchall()
    return [
        {"id": row["id"], "senderRole": row["sender_role"], "text": row["text"], "createdAt": row["created_at"]}
        for row in rows
    ]


def list_rooms(prefix: str) -> list[dict]:
    """prefix로 시작하는 대화방마다 마지막 메시지·개수·종료 상태."""
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT m.room, m.text, m.created_at, c.cnt, e.status
            FROM messages m
            JOIN (
                SELECT room, COUNT(*) AS cnt, MAX(rowid) AS last_id
                FROM messages WHERE substr(room, 1, ?) = ? GROUP BY room
            ) c ON m.rowid = c.last_id
            LEFT JOIN end_states e ON e.room = m.room
            """,
            (len(prefix), prefix),
        ).fetchall()
    return [
        {
            "room": row["room"],
            "lastMessage": row["text"],
            "lastAt": row["created_at"],
            "messageCount": row["cnt"],
            "status": row["status"] or "active",
        }
        for row in rows
    ]


# ---- 대화 종료 상태 ----
def get_end_state(room: str) -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT status, requested_by, declined_by FROM end_states WHERE room = ?", (room,)
        ).fetchone()
    if row is None:
        return {"status": "active", "requestedBy": None, "declinedBy": None}
    return {"status": row["status"], "requestedBy": row["requested_by"], "declinedBy": row["declined_by"]}


def save_end_state(room: str, state: dict) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO end_states VALUES (?, ?, ?, ?)",
            (room, state["status"], state["requestedBy"], state["declinedBy"]),
        )
