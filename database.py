"""
database.py — SQLite database layer for the Workout Tracker Bot.

Tables:
  users       – one row per Telegram user
  workouts    – one row per logged exercise entry
  body_weight – one row per daily body weight measurement
"""

import sqlite3
from datetime import datetime, timezone

DB_NAME = "workouts.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the tables if they don't already exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username    TEXT,
            created_at  TEXT    NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS workouts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            date          TEXT    NOT NULL,
            exercise_name TEXT    NOT NULL,
            sets          INTEGER NOT NULL,
            reps          INTEGER NOT NULL,
            weight_kg     REAL    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS body_weight (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            date      TEXT    NOT NULL,
            weight_kg REAL    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    conn.commit()
    conn.close()


def get_or_create_user(telegram_id: int, username: str | None) -> int:
    """
    Return the internal user id for a Telegram user.
    Creates a new row if this is the first interaction.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()

    if row:
        user_id = row["id"]
    else:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
            (telegram_id, username, now),
        )
        conn.commit()
        user_id = cursor.lastrowid

    conn.close()
    return user_id


# ── Workout CRUD ─────────────────────────────────────────────────────────

def add_workout(
    user_id: int,
    exercise_name: str,
    sets: int,
    reps: int,
    weight_kg: float,
) -> int:
    """Insert a new workout entry for today's date. Returns the row id."""
    conn = get_connection()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cursor = conn.execute(
        """
        INSERT INTO workouts (user_id, date, exercise_name, sets, reps, weight_kg)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, today, exercise_name, sets, reps, weight_kg),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def delete_workout(workout_id: int) -> bool:
    """Delete a workout entry by its id. Returns True if a row was deleted."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_exercise_history(user_id: int, exercise_name: str) -> list[dict]:
    """
    Fetch every logged entry for a given exercise, ordered by date.
    Returns a list of dicts with keys: date, sets, reps, weight_kg.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT date, sets, reps, weight_kg
        FROM workouts
        WHERE user_id = ? AND LOWER(exercise_name) = LOWER(?)
        ORDER BY date ASC
        """,
        (user_id, exercise_name),
    )

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ── Body weight CRUD ─────────────────────────────────────────────────────

def add_body_weight(user_id: int, weight_kg: float) -> int:
    """Insert a body weight entry for today. Returns the row id."""
    conn = get_connection()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cursor = conn.execute(
        """
        INSERT INTO body_weight (user_id, date, weight_kg)
        VALUES (?, ?, ?)
        """,
        (user_id, today, weight_kg),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_body_weight_history(user_id: int) -> list[dict]:
    """
    Fetch all body weight entries for a user, ordered by date.
    Returns a list of dicts with keys: date, weight_kg.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT date, weight_kg
        FROM body_weight
        WHERE user_id = ?
        ORDER BY date ASC
        """,
        (user_id,),
    )

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
