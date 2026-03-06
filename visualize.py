"""
visualize.py — Thread-safe chart generation for the Workout Tracker Bot.

Uses ONLY the matplotlib OO API (Figure + FigureCanvasAgg).
No pyplot import — prevents RecursionError in PTB's webhook environment.

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
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from database import get_exercise_history, get_body_weight_history

# Lock to serialize chart generation (matplotlib is not thread-safe)
_chart_lock = threading.Lock()

# ── Design tokens ────────────────────────────────────────────────────────
_BG_COLOR = "#1A1A2E"
_CARD_COLOR = "#16213E"
_GRID_COLOR = "#2A2A4A"
_TEXT_COLOR = "#E0E0E0"
_SUBTLE_TEXT = "#8888AA"

_ACCENT_BLUE = "#00D2FF"
_ACCENT_ORANGE = "#FF6B35"
_ACCENT_GREEN = "#00E676"
_ACCENT_RED = "#FF5252"
_ACCENT_PURPLE = "#BB86FC"

_GRADIENT_BLUE = "#0A1628"
_GRADIENT_GREEN = "#0A2818"


def _render_chart(fig: Figure, canvas: FigureCanvasAgg) -> bytes:
    """Render a Figure to PNG bytes and clean up."""
    try:
        buf = io.BytesIO()
        canvas.print_png(buf)
        png_bytes = buf.getvalue()
        buf.close()
        return png_bytes
    finally:
        for ax in fig.axes:
            ax.clear()
        fig.clear()
        del canvas


def _style_ax(ax, title: str) -> None:
    """Apply dark-themed styling to an axes object."""
    ax.set_facecolor(_CARD_COLOR)
    ax.set_title(
        title,
        fontsize=16, fontweight="bold", pad=16,
        color=_TEXT_COLOR, loc="left",
    )
    ax.tick_params(axis="both", labelsize=9, colors=_SUBTLE_TEXT)
    ax.tick_params(axis="x", rotation=40)
    ax.grid(True, linestyle="--", alpha=0.3, color=_GRID_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_GRID_COLOR)
    ax.spines["bottom"].set_color(_GRID_COLOR)


def generate_progress_chart(user_id: int, exercise_name: str) -> bytes | None:
    """
    Build a chart of weight over time for the given exercise.
    Shows ALL individual entries (not grouped).
    Returns raw PNG bytes, or None if insufficient data.
    """
    try:
        rows = get_exercise_history(user_id, exercise_name)
        if not rows or len(rows) < 2:
            return None

        # Build DataFrame — use .assign() to avoid chained-assignment warnings
        df = (
            pd.DataFrame(rows)
            .assign(
                date=lambda d: pd.to_datetime(d["date"]),
                weight_kg=lambda d: d["weight_kg"].astype(float),
                sets=lambda d: d["sets"].astype(int),
                reps=lambda d: d["reps"].astype(int),
            )
            .sort_values("date")
            .reset_index(drop=True)
        )

        dates = df["date"].tolist()
        weights = df["weight_kg"].tolist()
        sets_list = df["sets"].tolist()
        reps_list = df["reps"].tolist()

        with _chart_lock:
            fig = Figure(figsize=(10, 6), facecolor=_BG_COLOR, dpi=120)
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)

            _style_ax(ax, f"Progressive Overload  --  {exercise_name.title()}")

            # Main line with gradient fill
            ax.plot(
                dates, weights,
                marker="o", linestyle="-", color=_ACCENT_BLUE,
                linewidth=2.5, markersize=7,
                markerfacecolor=_ACCENT_ORANGE, markeredgecolor=_BG_COLOR,
                markeredgewidth=1.5, zorder=3,
            )
            ax.fill_between(dates, weights, alpha=0.12, color=_ACCENT_BLUE)

            # Annotate every point with weight + sets x reps
            for i in range(len(dates)):
                label = f"{weights[i]:.1f}kg\n{sets_list[i]}x{reps_list[i]}"
                ax.annotate(
                    label,
                    xy=(dates[i], weights[i]),
                    textcoords="offset points", xytext=(0, 14),
                    ha="center", fontsize=7, fontweight="bold",
                    color=_ACCENT_BLUE,
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor=_BG_COLOR, edgecolor=_ACCENT_BLUE,
                        alpha=0.85,
                    ),
                )

            # Trend line
            if len(dates) >= 3:
                x_num = mdates.date2num(dates)
                z = np.polyfit(x_num, weights, 1)
                p = np.poly1d(z)
                ax.plot(
                    dates, p(x_num),
                    linestyle="--", color=_ACCENT_PURPLE,
                    linewidth=1.5, alpha=0.6, zorder=2,
                    label="Trend",
                )
                ax.legend(
                    loc="upper left", fontsize=8,
                    facecolor=_CARD_COLOR, edgecolor=_GRID_COLOR,
                    labelcolor=_TEXT_COLOR,
                )

            ax.set_xlabel("Date", fontsize=10, color=_SUBTLE_TEXT, labelpad=8)
            ax.set_ylabel("Weight (kg)", fontsize=10, color=_SUBTLE_TEXT, labelpad=8)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

            # Add min/max summary
            min_w, max_w = min(weights), max(weights)
            diff = max_w - min_w
            summary = f"Min: {min_w:.1f}kg  |  Max: {max_w:.1f}kg  |  Range: {diff:.1f}kg"
            fig.text(
                0.5, 0.01, summary,
                ha="center", fontsize=9, color=_SUBTLE_TEXT,
                style="italic",
            )

            fig.tight_layout(rect=[0, 0.04, 1, 1])
            return _render_chart(fig, canvas)

    except Exception:
        print("=== ERROR in generate_progress_chart ===")
        traceback.print_exc()
        print("========================================")
        return None


def generate_body_weight_chart(user_id: int) -> bytes | None:
    """
    Build a chart of body weight over time.
    Shows ALL individual entries (not grouped).
    Returns raw PNG bytes, or None if insufficient data.
    """
    try:
        rows = get_body_weight_history(user_id)
        if not rows or len(rows) < 2:
            return None

        # Build DataFrame — use .assign() to avoid chained-assignment warnings
        df = (
            pd.DataFrame(rows)
            .assign(
                date=lambda d: pd.to_datetime(d["date"]),
                weight_kg=lambda d: d["weight_kg"].astype(float),
            )
            .sort_values("date")
            .reset_index(drop=True)
        )

        dates = df["date"].tolist()
        weights = df["weight_kg"].tolist()

        with _chart_lock:
            fig = Figure(figsize=(10, 6), facecolor=_BG_COLOR, dpi=120)
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_subplot(111)

            _style_ax(ax, "Body Weight Progression")

            # Main line
            ax.plot(
                dates, weights,
                marker="o", linestyle="-", color=_ACCENT_GREEN,
                linewidth=2.5, markersize=7,
                markerfacecolor=_ACCENT_RED, markeredgecolor=_BG_COLOR,
                markeredgewidth=1.5, zorder=3,
            )
            ax.fill_between(dates, weights, alpha=0.12, color=_ACCENT_GREEN)

            # Annotate every point
            for i in range(len(dates)):
                # Show change from previous
                change_str = ""
                if i > 0:
                    diff = weights[i] - weights[i - 1]
                    arrow = "+" if diff >= 0 else ""
                    change_str = f"\n{arrow}{diff:.1f}"

                label = f"{weights[i]:.1f}kg{change_str}"
                ax.annotate(
                    label,
                    xy=(dates[i], weights[i]),
                    textcoords="offset points", xytext=(0, 14),
                    ha="center", fontsize=7, fontweight="bold",
                    color=_ACCENT_GREEN,
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor=_BG_COLOR, edgecolor=_ACCENT_GREEN,
                        alpha=0.85,
                    ),
                )

            # Trend line
            if len(dates) >= 3:
                x_num = mdates.date2num(dates)
                z = np.polyfit(x_num, weights, 1)
                p = np.poly1d(z)
                ax.plot(
                    dates, p(x_num),
                    linestyle="--", color=_ACCENT_PURPLE,
                    linewidth=1.5, alpha=0.6, zorder=2,
                    label="Trend",
                )
                ax.legend(
                    loc="upper left", fontsize=8,
                    facecolor=_CARD_COLOR, edgecolor=_GRID_COLOR,
                    labelcolor=_TEXT_COLOR,
                )

            ax.set_xlabel("Date", fontsize=10, color=_SUBTLE_TEXT, labelpad=8)
            ax.set_ylabel("Weight (kg)", fontsize=10, color=_SUBTLE_TEXT, labelpad=8)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

            # Summary stats
            first_w, last_w = weights[0], weights[-1]
            total_change = last_w - first_w
            arrow = "+" if total_change >= 0 else ""
            summary = (
                f"Start: {first_w:.1f}kg  |  "
                f"Current: {last_w:.1f}kg  |  "
                f"Change: {arrow}{total_change:.1f}kg"
            )
            fig.text(
                0.5, 0.01, summary,
                ha="center", fontsize=9, color=_SUBTLE_TEXT,
                style="italic",
            )

            fig.tight_layout(rect=[0, 0.04, 1, 1])
            return _render_chart(fig, canvas)

    except Exception:
        print("=== ERROR in generate_body_weight_chart ===")
        traceback.print_exc()
        print("============================================")
        return None
