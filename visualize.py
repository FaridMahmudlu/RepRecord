"""
visualize.py — Chart generation for the Workout Tracker Bot.

Uses pandas + matplotlib to create:
  • Progressive-overload line charts (exercise weight over time)
  • Body weight progression charts
"""

import os
import tempfile

import matplotlib
matplotlib.use("Agg")  # non-interactive backend (no GUI needed)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from database import get_exercise_history, get_body_weight_history


def generate_progress_chart(user_id: int, exercise_name: str) -> str | None:
    """
    Build a line chart of weight over time for the given exercise.

    Returns the absolute path to the saved PNG image, or None if there
    is no data to plot.
    """
    rows = get_exercise_history(user_id, exercise_name)
    if not rows:
        return None

    # --- Build a DataFrame ------------------------------------------------
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    # If multiple entries on the same day, keep the heaviest weight
    df = df.groupby("date", as_index=False).agg({"weight_kg": "max", "sets": "max", "reps": "max"})
    df.sort_values("date", inplace=True)

    # --- Plot -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        df["date"],
        df["weight_kg"],
        marker="o",
        linewidth=2,
        color="#4A90D9",
        markerfacecolor="#F5A623",
        markersize=8,
    )

    # Annotate each data point with its weight
    for _, row in df.iterrows():
        ax.annotate(
            f'{row["weight_kg"]:.1f} kg',
            xy=(row["date"], row["weight_kg"]),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=9,
            fontweight="bold",
            color="#333333",
        )

    ax.set_title(
        f"Progressive Overload — {exercise_name.title()}",
        fontsize=16,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Weight (kg)", fontsize=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()

    # Save to a temp file that persists until the caller deletes it
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(tmp.name, dpi=150)
    plt.close(fig)

    return tmp.name


def generate_body_weight_chart(user_id: int) -> str | None:
    """
    Build a line chart of body weight over time.

    Returns the absolute path to the saved PNG image, or None if there
    is no data to plot.
    """
    rows = get_body_weight_history(user_id)
    if not rows:
        return None

    # --- Build a DataFrame ------------------------------------------------
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    # If multiple entries on the same day, keep the latest (last inserted)
    df = df.groupby("date", as_index=False).agg({"weight_kg": "last"})
    df.sort_values("date", inplace=True)

    # --- Plot -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        df["date"],
        df["weight_kg"],
        marker="o",
        linewidth=2,
        color="#27AE60",
        markerfacecolor="#E74C3C",
        markersize=8,
    )

    # Annotate each data point
    for _, row in df.iterrows():
        ax.annotate(
            f'{row["weight_kg"]:.1f} kg',
            xy=(row["date"], row["weight_kg"]),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=9,
            fontweight="bold",
            color="#333333",
        )

    ax.set_title(
        "Body Weight Progression",
        fontsize=16,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Weight (kg)", fontsize=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    fig.savefig(tmp.name, dpi=150)
    plt.close(fig)

    return tmp.name
