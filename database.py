# ============================================================
# database.py  —  Aria Bot · SQLite Manager
# ============================================================

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger("aria.db")

# ─────────────────────────── Schema ──────────────────────────

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS channel_settings (
    guild_id    INTEGER NOT NULL,
    role        TEXT    NOT NULL,  -- 'command' | 'chat' | 'ideas' | 'logs'
    channel_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role)
);

CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    owner_id        INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    description     TEXT,
    category_id     INTEGER,
    channel_id      INTEGER,
    status          TEXT    DEFAULT 'planning',   -- planning | active | done
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    actor_id    INTEGER,
    action      TEXT    NOT NULL,
    detail      TEXT,
    created_at  TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER NOT NULL,
    role        TEXT    NOT NULL,   -- 'user' | 'model'
    content     TEXT    NOT NULL,
    created_at  TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS authorized_users (
    user_id     INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    level       INTEGER DEFAULT 1,  -- 1=operator, 99=owner
    added_at    TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_builds (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version          INTEGER NOT NULL DEFAULT 1,
    triggered_by     INTEGER NOT NULL,            -- Discord user ID
    channel_snapshot TEXT,                        -- raw channel history used for this build
    generated_code   TEXT,                        -- full output from Gemini
    discord_msg_ids  TEXT,                        -- JSON list of message IDs posted
    status           TEXT    DEFAULT 'pending',  -- pending | building | done | failed
    created_at       TEXT    DEFAULT (datetime('now')),
    completed_at     TEXT
);
"""

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Create all tables if they don't exist."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
    log.info("Database initialised at %s", config.DB_PATH)

# ─────────────────── Channel Settings ────────────────────────

def set_channel(guild_id: int, role: str, channel_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO channel_settings (guild_id, role, channel_id) VALUES (?,?,?)",
            (guild_id, role, channel_id),
        )

def get_channel(guild_id: int, role: str) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT channel_id FROM channel_settings WHERE guild_id=? AND role=?",
            (guild_id, role),
        ).fetchone()
        return int(row["channel_id"]) if row else None

def get_all_channels(guild_id: int) -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, channel_id FROM channel_settings WHERE guild_id=?",
            (guild_id,),
        ).fetchall()
        return {r["role"]: int(r["channel_id"]) for r in rows}

# ─────────────────── Projects ────────────────────────────────

def create_project(guild_id: int, owner_id: int, name: str,
                   description: str = "", category_id: int = None,
                   channel_id: int = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO projects (guild_id, owner_id, name, description, category_id, channel_id)
            VALUES (?,?,?,?,?,?)""",
            (guild_id, owner_id, name, description, category_id, channel_id),
        )
        return cur.lastrowid

def get_project(project_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()

def list_projects(guild_id: int, status: str = None) -> list[sqlite3.Row]:
    with _connect() as conn:
        if status:
            return conn.execute(
                "SELECT * FROM projects WHERE guild_id=? AND status=? ORDER BY created_at DESC",
                (guild_id, status),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM projects WHERE guild_id=? ORDER BY created_at DESC",
            (guild_id,),
        ).fetchall()

def update_project_status(project_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE projects SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, project_id),
        )

# ─────────────────── Project Logs ────────────────────────────

def add_project_log(project_id: int, actor_id: int, action: str, detail: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO project_logs (project_id, actor_id, action, detail) VALUES (?,?,?,?)",
            (project_id, actor_id, action, detail),
        )

def get_project_logs(project_id: int, limit: int = 50) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM project_logs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()

# ─────────────────── Conversation History ────────────────────

def append_history(channel_id: int, role: str, content: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversation_history (channel_id, role, content) VALUES (?,?,?)",
            (channel_id, role, content),
        )
        # Keep last 100 messages per channel to cap memory
        conn.execute(
            """DELETE FROM conversation_history WHERE id NOT IN (
            SELECT id FROM conversation_history WHERE channel_id=?
            ORDER BY created_at DESC LIMIT 100)
            AND channel_id=?""",
            (channel_id, channel_id),
        )

def get_history(channel_id: int, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversation_history WHERE channel_id=? ORDER BY created_at ASC LIMIT ?",
            (channel_id, limit),
        ).fetchall()
        return [{"role": r["role"], "parts": [r["content"]]} for r in rows]

def clear_history(channel_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM conversation_history WHERE channel_id=?", (channel_id,))

# ─────────────────── Authorized Users ────────────────────────

def authorize_user(user_id: int, guild_id: int, level: int = 1) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO authorized_users (user_id, guild_id, level) VALUES (?,?,?)",
            (user_id, guild_id, level),
        )

def is_authorized(user_id: int, guild_id: int) -> bool:
    """Owner is always authorized; others must be in the table."""
    if user_id == config.OWNER_ID:
        return True
    with _connect() as conn:
        row = conn.execute(
            "SELECT level FROM authorized_users WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        ).fetchone()
        return row is not None

# ─────────────────── Project Builds (Versioned) ──────────────

def next_build_version(project_id: int) -> int:
    """Return the next sequential build version number for a project."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM project_builds WHERE project_id=?",
            (project_id,),
        ).fetchone()
        return int(row["v"]) + 1

def create_build(project_id: int, triggered_by: int, version: int,
                 channel_snapshot: str = "") -> int:
    """Insert a new build record and return its ID."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO project_builds
            (project_id, version, triggered_by, channel_snapshot, status)
            VALUES (?,?,?,?,'pending')""",
            (project_id, version, triggered_by, channel_snapshot),
        )
        return cur.lastrowid

def finish_build(build_id: int, generated_code: str,
                 discord_msg_ids: str, status: str = "done") -> None:
    """Persist the generated output and mark the build complete."""
    with _connect() as conn:
        conn.execute(
            """UPDATE project_builds
            SET generated_code=?, discord_msg_ids=?, status=?,
            completed_at=datetime('now')
            WHERE id=?""",
            (generated_code, discord_msg_ids, status, build_id),
        )

def fail_build(build_id: int, reason: str) -> None:
    finish_build(build_id, reason, "[]", status="failed")

def get_build(build_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM project_builds WHERE id=?", (build_id,)
        ).fetchone()

def list_builds(project_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM project_builds WHERE project_id=? ORDER BY version ASC",
            (project_id,),
        ).fetchall()

def get_project_by_channel(channel_id: int) -> Optional[sqlite3.Row]:
    """Look up a project given its Discord channel ID."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM projects WHERE channel_id=?", (channel_id,)
        ).fetchone()
