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
            CREATE TABLE IF NOT EXISTS juniors (
                junior_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL UNIQUE,
                pin_salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS junior_tokens (
                token_hash TEXT PRIMARY KEY,
                junior_id TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                mentor_id TEXT NOT NULL,
                junior_id TEXT NOT NULL,
                reporter_role TEXT NOT NULL,
                reason TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
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


def has_mentor_account(mentor_id: str) -> bool:
    with _db() as conn:
        return conn.execute("SELECT 1 FROM mentors WHERE mentor_id = ?", (mentor_id,)).fetchone() is not None


def add_mentor(mentor_id: str, display_name: str, major: str, status: str, bio: str, pin: str) -> None:
    """PIN은 솔트를 붙인 해시로만 저장한다. 닉네임이 겹치면 sqlite3.IntegrityError."""
    salt = secrets.token_hex(16)
    with _db() as conn:
        conn.execute(
            "INSERT INTO mentors VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mentor_id, display_name, major, status, bio, salt, _hash_pin(pin, salt), _now()),
        )


def update_mentor_bio(mentor_id: str, bio: str) -> bool:
    """Update a registered mentor's introduction without changing account credentials."""
    with _db() as conn:
        cursor = conn.execute(
            "UPDATE mentors SET bio = ? WHERE mentor_id = ?",
            (bio, mentor_id),
        )
        return cursor.rowcount > 0


# 선배·후배 계정이 쓰는 테이블 이름 (코드 안의 고정값만 SQL에 넣음)
_ACCOUNTS = {
    "senior": ("mentors", "mentor_id", "tokens"),
    "junior": ("juniors", "junior_id", "junior_tokens"),
}


def _check_pin(kind: str, display_name: str, pin: str) -> str | None:
    table, id_col, _ = _ACCOUNTS[kind]
    with _db() as conn:
        row = conn.execute(
            f"SELECT {id_col} AS id, pin_salt, pin_hash FROM {table} WHERE display_name = ?",
            (display_name,),
        ).fetchone()
    if row is None:
        return None
    if not hmac.compare_digest(_hash_pin(pin, row["pin_salt"]), row["pin_hash"]):
        return None
    return row["id"]


def check_pin(display_name: str, pin: str) -> str | None:
    """선배 닉네임과 PIN이 맞으면 mentor_id, 아니면 None."""
    return _check_pin("senior", display_name, pin)


# ---- 로그인 토큰 (DB에는 토큰 해시만 저장) ----
def _create_token(kind: str, owner_id: str) -> str:
    _, _, table = _ACCOUNTS[kind]
    token = secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute(f"INSERT INTO {table} VALUES (?, ?, ?)", (_hash_token(token), owner_id, _now()))
    return token


def _token_owner(kind: str, token: str) -> str | None:
    if not token:
        return None
    _, id_col, table = _ACCOUNTS[kind]
    with _db() as conn:
        row = conn.execute(
            f"SELECT {id_col} AS id, created_at FROM {table} WHERE token_hash = ?", (_hash_token(token),)
        ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["created_at"]) < datetime.now(timezone.utc) - timedelta(days=TOKEN_DAYS):
        _delete_token(kind, token)
        return None
    return row["id"]


def _delete_token(kind: str, token: str) -> None:
    _, _, table = _ACCOUNTS[kind]
    with _db() as conn:
        conn.execute(f"DELETE FROM {table} WHERE token_hash = ?", (_hash_token(token),))


def create_token(mentor_id: str) -> str:
    return _create_token("senior", mentor_id)


def token_mentor(token: str) -> str | None:
    return _token_owner("senior", token)


def delete_token(token: str) -> None:
    _delete_token("senior", token)


# ---- 후배 계정 ----
def add_junior(display_name: str, pin: str) -> str:
    """후배를 저장하고 새 juniorId(J-영문숫자 8자)를 돌려준다. 닉네임이 겹치면 sqlite3.IntegrityError."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    salt = secrets.token_hex(16)
    pin_hash = _hash_pin(pin, salt)
    with _db() as conn:
        while True:
            junior_id = "J-" + "".join(secrets.choice(chars) for _ in range(8))
            if conn.execute("SELECT 1 FROM juniors WHERE junior_id = ?", (junior_id,)).fetchone() is None:
                break
        conn.execute(
            "INSERT INTO juniors VALUES (?, ?, ?, ?, ?)",
            (junior_id, display_name, salt, pin_hash, _now()),
        )
    return junior_id


def check_junior_pin(display_name: str, pin: str) -> str | None:
    return _check_pin("junior", display_name, pin)


def junior_exists(display_name: str) -> bool:
    with _db() as conn:
        return conn.execute(
            "SELECT 1 FROM juniors WHERE display_name = ?", (display_name.strip(),)
        ).fetchone() is not None


def junior_names(junior_ids: list[str]) -> dict[str, str]:
    if not junior_ids:
        return {}
    marks = ",".join("?" * len(junior_ids))
    with _db() as conn:
        rows = conn.execute(
            f"SELECT junior_id, display_name FROM juniors WHERE junior_id IN ({marks})", junior_ids
        ).fetchall()
    return {row["junior_id"]: row["display_name"] for row in rows}


def create_junior_token(junior_id: str) -> str:
    return _create_token("junior", junior_id)


def token_junior(token: str) -> str | None:
    return _token_owner("junior", token)


def delete_junior_token(token: str) -> None:
    _delete_token("junior", token)


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


def list_recent_messages(limit: int = 80) -> list[dict]:
    """학교 챗봇용: 최근 메시지를 역할·내용만 가져와 ID는 빼 둔다."""
    limit = max(1, min(int(limit), 200))
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT sender_role, text, created_at
            FROM messages
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    # 시간순(오래된 것 → 최신)으로 뒤집어서 문맥이 자연스럽게
    rows = list(reversed(rows))
    return [
        {
            "senderRole": row["sender_role"],
            "text": row["text"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def list_rooms(prefix: str = "", suffix: str = "") -> list[dict]:
    """prefix로 시작하고 suffix로 끝나는 대화방마다 마지막 메시지·보낸 쪽·개수·종료 상태."""
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT m.room, m.text, m.sender_role, m.created_at, c.cnt, e.status
            FROM messages m
            JOIN (
                SELECT room, COUNT(*) AS cnt, MAX(rowid) AS last_id
                FROM messages
                WHERE substr(room, 1, ?) = ? AND (? = 0 OR substr(room, -?) = ?)
                GROUP BY room
            ) c ON m.rowid = c.last_id
            LEFT JOIN end_states e ON e.room = m.room
            """,
            (len(prefix), prefix, len(suffix), len(suffix), suffix),
        ).fetchall()
    return [
        {
            "room": row["room"],
            "lastMessage": row["text"],
            "lastAt": row["created_at"],
            "lastSenderRole": row["sender_role"],
            "messageCount": row["cnt"],
            "status": row["status"] or "active",
        }
        for row in rows
    ]


# ---- 신고 ----
def _report_dict(row: sqlite3.Row) -> dict:
    return {
        "reportId": row["report_id"],
        "mentorId": row["mentor_id"],
        "juniorId": row["junior_id"],
        "reporterRole": row["reporter_role"],
        "reason": row["reason"],
        "details": row["details"],
        "createdAt": row["created_at"],
    }


def add_report(report: dict) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                report["reportId"],
                report["mentorId"],
                report["juniorId"],
                report["reporterRole"],
                report["reason"],
                report["details"],
                report["createdAt"],
            ),
        )


def list_reports() -> list[dict]:
    """신고 전체(최근순)."""
    with _db() as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    return [_report_dict(row) for row in rows]


def get_report(report_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM reports WHERE report_id = ?", (report_id,)).fetchone()
    return _report_dict(row) if row else None


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
