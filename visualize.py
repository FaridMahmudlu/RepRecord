"""
visualize.py — Thread-safe chart generation for the Workout Tracker Bot.

Uses ONLY the matplotlib OO API (Figure + FigureCanvasAgg).
No pyplot import — this prevents RecursionError caused by PTB's deepcopy
of leaked matplotlib global state in the webhook/async environment.

Charts are returned as raw bytes — never Figure, Axes, or BytesIO objects.
"""

import copy as _copy_module
import io
import traceback
import threading

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend (MUST be before any mpl imports)

# ── Fix matplotlib 3.10.x + Python 3.14 incompatibility ─────────────────
# Path.__deepcopy__ calls copy.deepcopy(super(), memo) which causes infinite
# recursion: each super() proxy has a unique id(), defeating memo dedup.
import matplotlib.path as _mpath


def _patched_path_deepcopy(self, memo):
    """Fixed Path.__deepcopy__ — bypasses the broken super() call."""
    if id(self) in memo:
        return memo[id(self)]
    cls = type(self)
    result = cls(
        _copy_module.deepcopy(self.vertices, memo),
        _copy_module.deepcopy(self.codes, memo) if self.codes is not None else None,
    )
    memo[id(self)] = result
    result._readonly = False
    return result


_mpath.Path.__deepcopy__ = _patched_path_deepcopy
# ─────────────────────────────────────────────────────────────────────────

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.dates as mdates
import pandas as pd

from database import get_exercise_history, get_body_weight_history

# Lock to serialize chart generation (matplotlib is not thread-safe)
_chart_lock = threading.Lock()


def _render_chart(fig: Figure, canvas: FigureCanvasAgg) -> bytes:
    """Render a Figure to PNG bytes and clean up. Helper to avoid duplication."""
    try:
        buf = io.BytesIO()
        canvas.print_png(buf)
        png_bytes = buf.getvalue()
        buf.close()
        return png_bytes
    finally:
        # OO-only cleanup — no pyplot interaction at all
        for ax in fig.axes:
            ax.clear()
        fig.clear()
        del canvas


def generate_progress_chart(user_id: int, exercise_name: str) -> bytes | None:
    """
    Build a line chart of weight over time for the given exercise.
    Returns raw PNG bytes, or None if no data / insufficient data.
    """
    try:
        rows = get_exercise_history(user_id, exercise_name)
        if not rows:
            return None

        # --- Build a DataFrame with explicit Python types ---------------------
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

        # Guard: need at least 2 points to draw a meaningful chart
        if len(df) < 2:
            return None

        dates = df["date"].tolist()
        values = df["weight_kg"].tolist()

        # --- Thread-safe plot (pure OO API, no pyplot) ----------------------
        with _chart_lock:
            fig = Figure(figsize=(10, 6), facecolor="#FFFFFF")
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)

            # Main line
            ax.plot(
                dates, values,
                marker="o", linestyle="-", color="#2E86AB",
                linewidth=2.5, markersize=8,
                markerfacecolor="#F18F01", markeredgecolor="#FFFFFF",
                markeredgewidth=1.5, zorder=3,
            )

            # Fill area under the curve
            ax.fill_between(dates, values, alpha=0.08, color="#2E86AB")

            # Annotate each point
            for i in range(len(dates)):
                ax.annotate(
                    f'{values[i]:.1f} kg',
                    xy=(dates[i], values[i]),
                    textcoords="offset points", xytext=(0, 14),
                    ha="center", fontsize=9, fontweight="bold", color="#2E86AB",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor="#2E86AB", alpha=0.8),
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
            ax.grid(True, linestyle="--", alpha=0.7, color="#E0E0E0")
            ax.set_facecolor("#FAFAFA")
            fig.tight_layout()

            return _render_chart(fig, canvas)

    except Exception:
        print("=== ERROR in generate_progress_chart ===")
        traceback.print_exc()
        print("========================================")
        return None


def generate_body_weight_chart(user_id: int) -> bytes | None:
    """
    Build a line chart of body weight over time.
    Returns raw PNG bytes, or None if no data / insufficient data.
    """
    try:
        rows = get_body_weight_history(user_id)
        if not rows:
            return None

        # --- Build a DataFrame with explicit Python types ---------------------
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["weight_kg"] = df["weight_kg"].astype(float)

        # If multiple entries on the same day, keep the latest
        df = df.groupby("date", as_index=False).agg({"weight_kg": "last"})
        df.sort_values("date", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Guard: need at least 2 points to draw a meaningful chart
        if len(df) < 2:
            return None

        dates = df["date"].tolist()
        values = df["weight_kg"].tolist()

        # --- Thread-safe plot (pure OO API, no pyplot) ----------------------
        with _chart_lock:
            fig = Figure(figsize=(10, 6), facecolor="#FFFFFF")
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)

            # Main line
            ax.plot(
                dates, values,
                marker="o", linestyle="-", color="#27AE60",
                linewidth=2.5, markersize=8,
                markerfacecolor="#E74C3C", markeredgecolor="#FFFFFF",
                markeredgewidth=1.5, zorder=3,
            )

            # Fill area under the curve
            ax.fill_between(dates, values, alpha=0.08, color="#27AE60")

            # Annotate each point
            for i in range(len(dates)):
                ax.annotate(
                    f'{values[i]:.1f} kg',
                    xy=(dates[i], values[i]),
                    textcoords="offset points", xytext=(0, 14),
                    ha="center", fontsize=9, fontweight="bold", color="#27AE60",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor="#27AE60", alpha=0.8),
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
            ax.grid(True, linestyle="--", alpha=0.7, color="#E0E0E0")
            ax.set_facecolor("#FAFAFA")
            fig.tight_layout()

            return _render_chart(fig, canvas)

    except Exception:
        print("=== ERROR in generate_body_weight_chart ===")
        traceback.print_exc()
        print("============================================")
        return None
