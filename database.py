"""
database.py — PostgreSQL database layer for the Workout Tracker Bot.

Tables:
  users       – one row per Telegram user
  workouts    – one row per logged exercise entry
  body_weight – one row per daily body weight measurement

Connection string is read from the DATABASE_URL environment variable.
SSL is enforced automatically for cloud providers (e.g. Supabase).
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone


def get_db_connection():
    """
    Create and return a new PostgreSQL connection.
    Appends sslmode=require if not already present.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    # Ensure SSL is enabled for cloud-hosted databases
    if "sslmode" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url += f"{separator}sslmode=require"

    return psycopg2.connect(database_url)


def init_db() -> None:
    """Create the tables if they don't already exist."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id          SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username    TEXT,
                    created_at  TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS workouts (
                    id            SERIAL PRIMARY KEY,
                    user_id       INTEGER NOT NULL REFERENCES users (id),
                    date          TEXT    NOT NULL,
                    exercise_name TEXT    NOT NULL,
                    sets          INTEGER NOT NULL,
                    reps          INTEGER NOT NULL,
                    weight_kg     REAL    NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS body_weight (
                    id        SERIAL PRIMARY KEY,
                    user_id   INTEGER NOT NULL REFERENCES users (id),
                    date      TEXT    NOT NULL,
                    weight_kg REAL    NOT NULL
                )
                """
            )

        conn.commit()


def get_or_create_user(telegram_id: int, username: str | None) -> int:
    """
    Return the internal user id for a Telegram user.
    Creates a new row if this is the first interaction.
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
            row = cursor.fetchone()

            if row:
                return row["id"]

            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO users (telegram_id, username, created_at) VALUES (%s, %s, %s) RETURNING id",
                (telegram_id, username, now),
            )
            user_id = cursor.fetchone()["id"]
            conn.commit()
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
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cursor.execute(
                """
                INSERT INTO workouts (user_id, date, exercise_name, sets, reps, weight_kg)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, today, exercise_name, sets, reps, weight_kg),
            )
            row_id = cursor.fetchone()["id"]
            conn.commit()
            return row_id


def delete_workout(workout_id: int) -> bool:
    """Delete a workout entry by its id. Returns True if a row was deleted."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM workouts WHERE id = %s", (workout_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted


def get_exercise_history(user_id: int, exercise_name: str) -> list[dict]:
    """
    Fetch every logged entry for a given exercise, ordered by date.
    Returns a list of dicts with keys: date, sets, reps, weight_kg.
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT date, sets, reps, weight_kg
                FROM workouts
                WHERE user_id = %s AND LOWER(exercise_name) = LOWER(%s)
                ORDER BY date ASC
                """,
                (user_id, exercise_name),
            )
            return [dict(r) for r in cursor.fetchall()]


# ── Body weight CRUD ─────────────────────────────────────────────────────

def add_body_weight(user_id: int, weight_kg: float) -> int:
    """Insert a body weight entry for today. Returns the row id."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cursor.execute(
                """
                INSERT INTO body_weight (user_id, date, weight_kg)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_id, today, weight_kg),
            )
            row_id = cursor.fetchone()["id"]
            conn.commit()
            return row_id


def get_body_weight_history(user_id: int) -> list[dict]:
    """
    Fetch all body weight entries for a user, ordered by date.
    Returns a list of dicts with keys: date, weight_kg.
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT date, weight_kg
                FROM body_weight
                WHERE user_id = %s
                ORDER BY date ASC
                """,
                (user_id,),
            )
            return [dict(r) for r in cursor.fetchall()]
