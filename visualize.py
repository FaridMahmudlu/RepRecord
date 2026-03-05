"""
visualize.py — Thread-safe chart generation for the Workout Tracker Bot.

Uses the matplotlib OO API exclusively (NO pyplot import) to avoid
RecursionError from PTB's deepcopy of leaked global state.
Charts are returned as in-memory BytesIO buffers — no temp files needed.
"""

import io
import threading

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.dates as mdates
import pandas as pd

from database import get_exercise_history, get_body_weight_history

# Lock to serialize chart generation (matplotlib is not thread-safe)
_chart_lock = threading.Lock()


def generate_progress_chart(user_id: int, exercise_name: str) -> io.BytesIO | None:
    """
    Build a line chart of weight over time for the given exercise.
    Returns a BytesIO PNG buffer, or None if no data.
    """
    rows = get_exercise_history(user_id, exercise_name)
    if not rows:
        return None

    # --- Build a DataFrame with explicit types ----------------------------
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["weight_kg"] = df["weight_kg"].astype(float)
    df["sets"] = df["sets"].astype(int)
    df["reps"] = df["reps"].astype(int)

    # If multiple entries on the same day, keep the heaviest weight
    df = df.groupby("date", as_index=False).agg(
        {"weight_kg": "max", "sets": "max", "reps": "max"}
    )
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # --- Thread-safe plot using pure OO API --------------------------------
    with _chart_lock:
        fig = Figure(figsize=(10, 6), facecolor="#FFFFFF")
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)

        # Main line
        ax.plot(
            df["date"].values,
            df["weight_kg"].values,
            marker="o",
            linestyle="-",
            color="#2E86AB",
            linewidth=2.5,
            markersize=8,
            markerfacecolor="#F18F01",
            markeredgecolor="#FFFFFF",
            markeredgewidth=1.5,
            zorder=3,
        )

        # Fill area under the curve
        ax.fill_between(
            df["date"].values,
            df["weight_kg"].values,
            alpha=0.08,
            color="#2E86AB",
        )

        # Annotate each point
        for _, row in df.iterrows():
            ax.annotate(
                f'{row["weight_kg"]:.1f} kg',
                xy=(row["date"], row["weight_kg"]),
                textcoords="offset points",
                xytext=(0, 14),
                ha="center",
                fontsize=9,
                fontweight="bold",
                color="#2E86AB",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    edgecolor="#2E86AB",
                    alpha=0.8,
                ),
            )

        ax.set_title(
            f"📈 Progressive Overload — {exercise_name.title()}",
            fontsize=17, fontweight="bold", pad=18, color="#1A1A2E",
        )
        ax.set_xlabel("Date", fontsize=12, color="#555555")
        ax.set_ylabel("Weight (kg)", fontsize=12, color="#555555")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.tick_params(axis="both", labelsize=10, colors="#555555")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, linestyle="--", alpha=0.6, color="#E0E0E0")
        ax.set_facecolor("#FAFAFA")
        fig.tight_layout()

        # Render to in-memory buffer
        buf = io.BytesIO()
        canvas.print_png(buf)
        buf.seek(0)

    return buf


def generate_body_weight_chart(user_id: int) -> io.BytesIO | None:
    """
    Build a line chart of body weight over time.
    Returns a BytesIO PNG buffer, or None if no data.
    """
    rows = get_body_weight_history(user_id)
    if not rows:
        return None

    # --- Build a DataFrame with explicit types ----------------------------
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["weight_kg"] = df["weight_kg"].astype(float)

    # If multiple entries on the same day, keep the latest
    df = df.groupby("date", as_index=False).agg({"weight_kg": "last"})
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # --- Thread-safe plot using pure OO API --------------------------------
    with _chart_lock:
        fig = Figure(figsize=(10, 6), facecolor="#FFFFFF")
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)

        # Main line
        ax.plot(
            df["date"].values,
            df["weight_kg"].values,
            marker="o",
            linestyle="-",
            color="#27AE60",
            linewidth=2.5,
            markersize=8,
            markerfacecolor="#E74C3C",
            markeredgecolor="#FFFFFF",
            markeredgewidth=1.5,
            zorder=3,
        )

        # Fill area under the curve
        ax.fill_between(
            df["date"].values,
            df["weight_kg"].values,
            alpha=0.08,
            color="#27AE60",
        )

        # Annotate each point
        for _, row in df.iterrows():
            ax.annotate(
                f'{row["weight_kg"]:.1f} kg',
                xy=(row["date"], row["weight_kg"]),
                textcoords="offset points",
                xytext=(0, 14),
                ha="center",
                fontsize=9,
                fontweight="bold",
                color="#27AE60",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    edgecolor="#27AE60",
                    alpha=0.8,
                ),
            )

        ax.set_title(
            "⚖️ Body Weight Progression",
            fontsize=17, fontweight="bold", pad=18, color="#1A1A2E",
        )
        ax.set_xlabel("Date", fontsize=12, color="#555555")
        ax.set_ylabel("Weight (kg)", fontsize=12, color="#555555")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.tick_params(axis="both", labelsize=10, colors="#555555")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, linestyle="--", alpha=0.6, color="#E0E0E0")
        ax.set_facecolor("#FAFAFA")
        fig.tight_layout()

        # Render to in-memory buffer
        buf = io.BytesIO()
        canvas.print_png(buf)
        buf.seek(0)

    return buf
