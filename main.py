"""
main.py — Personal Workout & Progress Tracker Bot (Interactive Button UI).

Features:
  • Persistent bottom keyboard with 4 buttons
  • Guided workout logging via inline buttons (muscle group → exercise → stats)
  • Undo last entry via inline button on confirmation message
  • Body weight logging & chart
  • Progress charts via inline button picker
  • Fallback: direct text like "Bench Press 3x10 80kg" still works
"""

import asyncio
import logging
import os
import re
import traceback

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import (
    add_body_weight,
    add_workout,
    delete_workout,
    get_all_weight_history,
    get_exercise_history,
    get_last_weight,
    get_last_workout_stat,
    get_or_create_user,
    init_db,
)
from visualize import generate_body_weight_chart, generate_progress_chart

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Exercise catalogue ───────────────────────────────────────────────────
EXERCISES: dict[str, list[str]] = {
    "Chest":     ["Incline Chest Press", "Flat Bench Press", "Cable Fly", "Dumbbell Fly"],
    "Back":      ["Pull-Up", "Barbell Row", "Lat Pulldown", "Seated Cable Row"],
    "Legs":      ["Squat", "Leg Press", "Romanian Deadlift", "Leg Curl"],
    "Shoulders": ["Overhead Press", "Lateral Raise", "Face Pull", "Arnold Press"],
    "Arms":      ["Bicep Curl", "Tricep Pushdown", "Hammer Curl", "Skull Crusher"],
}

MUSCLE_EMOJIS: dict[str, str] = {
    "Chest": "🫁", "Back": "🔙", "Legs": "🦵",
    "Shoulders": "💪", "Arms": "🦾",
}

# ── Persistent bottom keyboard ───────────────────────────────────────────
MAIN_MENU_KB = ReplyKeyboardMarkup(
    [
        ["🏋️ Log Workout", "📊 View Progress"],
        ["⚖️ Log Body Weight", "📈 Weight Chart"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ── ConversationHandler states ───────────────────────────────────────────
SELECT_MUSCLE, SELECT_EXERCISE, ENTER_STATS = range(3)
PROGRESS_MUSCLE, PROGRESS_EXERCISE = range(10, 12)
ENTER_BODY_WEIGHT = 20

# ── Regex fallback for direct text logging ───────────────────────────────
WORKOUT_RE = re.compile(
    r"^(?P<exercise>.+?)\s+"
    r"(?P<sets>\d+)\s*x\s*"
    r"(?P<reps>\d+)\s+"
    r"(?P<weight>[\d.]+)\s*kg$",
    re.IGNORECASE,
)


# ═════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════════════

def muscle_group_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Build an inline keyboard with one button per muscle group."""
    buttons = [
        [InlineKeyboardButton(
            f"{MUSCLE_EMOJIS.get(mg, '')} {mg}",
            callback_data=f"{prefix}:{mg}",
        )]
        for mg in EXERCISES
    ]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(buttons)


def exercise_keyboard(prefix: str, muscle_group: str) -> InlineKeyboardMarkup:
    """Build an inline keyboard with one button per exercise in a muscle group."""
    exercises = EXERCISES.get(muscle_group, [])
    buttons = [
        [InlineKeyboardButton(ex, callback_data=f"{prefix}:{ex}")]
        for ex in exercises
    ]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"{prefix}:back")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(buttons)


def undo_keyboard(workout_id: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard with a single 'Undo' button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Undo Last Entry", callback_data=f"undo:{workout_id}")]]
    )


# ═════════════════════════════════════════════════════════════════════════
#  /START COMMAND
# ═════════════════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greet the user and show the main menu keyboard."""
    welcome = (
        "🏋️ *Welcome to the Workout Tracker Bot!*\n\n"
        "Use the buttons below to get started:\n\n"
        "• *🏋️ Log Workout* — record an exercise\n"
        "• *📊 View Progress* — see your exercise charts\n"
        "• *⚖️ Log Body Weight* — track your body weight\n"
        "• *📈 Weight Chart* — see your weight trend\n\n"
        "You can also type workouts directly:\n"
        "`Incline Chest Press 4x10 60kg`\n\n"
        "Let's track your gains! 💪"
    )
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KB,
    )


# ═════════════════════════════════════════════════════════════════════════
#  UNDO HANDLER (standalone CallbackQueryHandler)
# ═════════════════════════════════════════════════════════════════════════

async def handle_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a workout entry when the user clicks the Undo button."""
    query = update.callback_query
    await query.answer()

    try:
        workout_id = int(query.data.removeprefix("undo:"))
        deleted = delete_workout(workout_id)

        if deleted:
            await query.edit_message_text("❌ Entry deleted successfully. No worries!")
        else:
            await query.edit_message_text("⚠️ Entry was already removed.")

    except Exception as exc:
        logger.error("Error undoing workout: %s", exc, exc_info=True)
        await query.edit_message_text("❌ Could not undo the entry. Please try again.")


# ═════════════════════════════════════════════════════════════════════════
#  WORKOUT LOGGING FLOW  (ConversationHandler)
# ═════════════════════════════════════════════════════════════════════════

async def log_workout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: show muscle group selection."""
    await update.message.reply_text(
        "💪 *Select a muscle group:*",
        parse_mode="Markdown",
        reply_markup=muscle_group_keyboard("log_mg"),
    )
    return SELECT_MUSCLE


async def log_select_muscle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked a muscle group — show exercises."""
    query = update.callback_query
    await query.answer()
    data = query.data.removeprefix("log_mg:")

    if data == "cancel":
        await query.edit_message_text("👌 Workout logging cancelled.")
        return ConversationHandler.END

    context.user_data["muscle_group"] = data
    await query.edit_message_text(
        f"🏋️ *{data}* — Select an exercise:",
        parse_mode="Markdown",
        reply_markup=exercise_keyboard("log_ex", data),
    )
    return SELECT_EXERCISE


async def log_select_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked an exercise — prompt for sets/reps/weight with last stats."""
    query = update.callback_query
    await query.answer()
    data = query.data.removeprefix("log_ex:")

    if data == "cancel":
        await query.edit_message_text("👌 Workout logging cancelled.")
        return ConversationHandler.END

    if data == "back":
        await query.edit_message_text(
            "💪 *Select a muscle group:*",
            parse_mode="Markdown",
            reply_markup=muscle_group_keyboard("log_mg"),
        )
        return SELECT_MUSCLE

    context.user_data["exercise"] = data

    # Smart UX: show last workout stats as a reminder
    prompt = f"📝 *{data}*\n\n"
    try:
        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)
        last = get_last_workout_stat(user_id, data)
        if last:
            prompt += (
                f"💡 _Last time: {int(last['sets'])} × {int(last['reps'])} "
                f"@ {float(last['weight_kg']):.1f} kg — try to beat it!_\n\n"
            )
    except Exception:
        pass  # Don't block the flow if DB lookup fails

    prompt += "Enter *sets*, *reps*, and *weight* (kg):\nExample: `4 10 60`"

    await query.edit_message_text(prompt, parse_mode="Markdown")
    return ENTER_STATS


async def log_enter_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed stats — parse, save, and confirm with undo button."""
    text = update.message.text.strip()

    # Parse: expect "sets reps weight"
    match = re.match(r"^(\d+)\s+(\d+)\s+([\d.]+)$", text)
    if not match:
        await update.message.reply_text(
            "⚠️ Please enter three numbers: *sets reps weight*\n"
            "Example: `4 10 60`",
            parse_mode="Markdown",
        )
        return ENTER_STATS

    try:
        sets = int(match.group(1))
        reps = int(match.group(2))
        weight = float(match.group(3))
        exercise = context.user_data["exercise"]

        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)
        workout_id = add_workout(user_id, exercise, sets, reps, weight)

        await update.message.reply_text(
            f"✅ *Workout logged!*\n\n"
            f"🏋️ Exercise: *{exercise}*\n"
            f"🔁 Sets × Reps: *{sets} × {reps}*\n"
            f"⚖️ Weight: *{weight} kg*\n\n"
            f"Keep pushing! 💪",
            parse_mode="Markdown",
            reply_markup=undo_keyboard(workout_id),
        )

    except Exception as exc:
        logger.error("Error logging workout: %s", exc, exc_info=True)
        await update.message.reply_text(
            "❌ Something went wrong while saving. Please try again.",
            reply_markup=MAIN_MENU_KB,
        )

    return ConversationHandler.END


async def log_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any conversation via /cancel."""
    await update.message.reply_text(
        "👌 Cancelled.",
        reply_markup=MAIN_MENU_KB,
    )
    return ConversationHandler.END


# ═════════════════════════════════════════════════════════════════════════
#  VIEW PROGRESS FLOW  (ConversationHandler)
# ═════════════════════════════════════════════════════════════════════════

async def progress_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: show muscle group picker for progress viewing."""
    await update.message.reply_text(
        "📊 *View Progress* — Select a muscle group:",
        parse_mode="Markdown",
        reply_markup=muscle_group_keyboard("prog_mg"),
    )
    return PROGRESS_MUSCLE


async def progress_select_muscle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked a muscle group — show exercises."""
    query = update.callback_query
    await query.answer()
    data = query.data.removeprefix("prog_mg:")

    if data == "cancel":
        await query.edit_message_text("👌 Progress view cancelled.")
        return ConversationHandler.END

    context.user_data["progress_muscle"] = data
    await query.edit_message_text(
        f"📊 *{data}* — Select an exercise:",
        parse_mode="Markdown",
        reply_markup=exercise_keyboard("prog_ex", data),
    )
    return PROGRESS_EXERCISE


async def progress_select_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked an exercise — generate and send chart."""
    query = update.callback_query
    await query.answer()
    data = query.data.removeprefix("prog_ex:")

    if data == "cancel":
        await query.edit_message_text("👌 Progress view cancelled.")
        return ConversationHandler.END

    if data == "back":
        await query.edit_message_text(
            "📊 *View Progress* — Select a muscle group:",
            parse_mode="Markdown",
            reply_markup=muscle_group_keyboard("prog_mg"),
        )
        return PROGRESS_MUSCLE

    exercise = data

    try:
        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)

        # Safety check: need at least 2 data points before plotting
        history = get_exercise_history(user_id, exercise)
        if not history or len(history) < 2:
            await query.edit_message_text(
                "Not enough data to draw a chart yet. Keep logging this exercise!"
            )
            return ConversationHandler.END

        chart_buf = generate_progress_chart(user_id, exercise)

        if chart_buf is None:
            await query.edit_message_text(
                f"📭 No data found for *{exercise}*.\n"
                "Log some workouts first!",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        await query.edit_message_text(f"📈 Generating chart for *{exercise}*…", parse_mode="Markdown")

        await query.message.reply_photo(
            photo=chart_buf,
            caption=f"📈 Your progress for *{exercise}*",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.error("Error in progress view: %s", exc, exc_info=True)
        traceback.print_exc()
        await query.edit_message_text(
            "❌ Something went wrong while generating your chart."
        )

    return ConversationHandler.END


# ═════════════════════════════════════════════════════════════════════════
#  BODY WEIGHT FLOW  (ConversationHandler)
# ═════════════════════════════════════════════════════════════════════════

async def body_weight_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: prompt user for their body weight, showing last recorded."""
    prompt = "⚖️ *Log Body Weight*\n\n"

    # Smart UX: show last recorded weight
    try:
        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)
        last_w = get_last_weight(user_id)
        if last_w is not None:
            prompt += f"💡 _Your last recorded weight was: {last_w:.1f} kg_\n\n"
    except Exception:
        pass

    prompt += "Enter your current weight in kg:\nExample: `75.5`"

    await update.message.reply_text(prompt, parse_mode="Markdown")
    return ENTER_BODY_WEIGHT


async def body_weight_enter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate, save, and show weight change."""
    text = update.message.text.strip()

    # Validate: must be a positive number
    try:
        weight = float(text)
        if weight <= 0 or weight > 500:
            raise ValueError("Out of range")
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a valid weight in kg (e.g. `75.5`).",
            parse_mode="Markdown",
        )
        return ENTER_BODY_WEIGHT

    try:
        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)

        # Get previous weight BEFORE inserting the new one
        prev_weight = get_last_weight(user_id)
        add_body_weight(user_id, weight)

        # Build change indicator
        change_text = ""
        if prev_weight is not None:
            diff = weight - prev_weight
            if diff > 0:
                change_text = f"\n📈 Change: *+{diff:.1f} kg*"
            elif diff < 0:
                change_text = f"\n📉 Change: *{diff:.1f} kg*"
            else:
                change_text = "\n➖ No change"

        await update.message.reply_text(
            f"✅ *Body weight logged!*\n\n"
            f"⚖️ Weight: *{weight} kg*{change_text}\n\n"
            f"Keep it up! 🎯",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_KB,
        )

    except Exception as exc:
        logger.error("Error logging body weight: %s", exc, exc_info=True)
        await update.message.reply_text(
            "❌ Something went wrong. Please try again.",
            reply_markup=MAIN_MENU_KB,
        )

    return ConversationHandler.END


# ═════════════════════════════════════════════════════════════════════════
#  WEIGHT CHART HANDLER
# ═════════════════════════════════════════════════════════════════════════

async def weight_chart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send the body weight progression chart (dedicated handler)."""
    try:
        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)

        # Check data sufficiency BEFORE calling matplotlib
        history = get_all_weight_history(user_id)
        if not history or len(history) < 2:
            await update.message.reply_text(
                "Not enough data to draw a chart yet. "
                "Please log your weight at least twice!",
                reply_markup=MAIN_MENU_KB,
            )
            return

        chart_buf = generate_body_weight_chart(user_id)

        if chart_buf is None:
            await update.message.reply_text(
                "📭 No body weight data found.\n"
                "Use *⚖️ Log Body Weight* to start tracking!",
                parse_mode="Markdown",
                reply_markup=MAIN_MENU_KB,
            )
            return

        await update.message.reply_photo(
            photo=chart_buf,
            caption="📈 Your body weight progression",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.error("Error generating weight chart: %s", exc, exc_info=True)
        traceback.print_exc()
        await update.message.reply_text(
            "❌ Something went wrong while generating the chart.",
            reply_markup=MAIN_MENU_KB,
        )


async def weight_chart_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper for weight_chart_handler when triggered as a ConversationHandler fallback."""
    await weight_chart_handler(update, context)
    return ConversationHandler.END


# ═════════════════════════════════════════════════════════════════════════
#  FALLBACK TEXT HANDLER  (direct "Bench Press 3x10 80kg" still works)
# ═════════════════════════════════════════════════════════════════════════

async def handle_text_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parse free-text workout entries as a fallback."""
    text = update.message.text.strip()
    match = WORKOUT_RE.match(text)

    if not match:
        if any(ch.isdigit() for ch in text):
            await update.message.reply_text(
                "🤔 I couldn't parse that.\n\n"
                "Use the *🏋️ Log Workout* button, or type:\n"
                "`Exercise Name SETSxREPS WEIGHTkg`\n"
                "Example: `Incline Chest Press 4x10 60kg`",
                parse_mode="Markdown",
                reply_markup=MAIN_MENU_KB,
            )
        return

    try:
        exercise = match.group("exercise").strip()
        sets = int(match.group("sets"))
        reps = int(match.group("reps"))
        weight = float(match.group("weight"))

        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)
        workout_id = add_workout(user_id, exercise, sets, reps, weight)

        await update.message.reply_text(
            f"✅ *Workout logged!*\n\n"
            f"🏋️ Exercise: *{exercise}*\n"
            f"🔁 Sets × Reps: *{sets} × {reps}*\n"
            f"⚖️ Weight: *{weight} kg*\n\n"
            f"Keep pushing! 💪",
            parse_mode="Markdown",
            reply_markup=undo_keyboard(workout_id),
        )

    except Exception as exc:
        logger.error("Error logging workout: %s", exc, exc_info=True)
        await update.message.reply_text(
            "❌ Something went wrong while saving your workout.",
            reply_markup=MAIN_MENU_KB,
        )


# ═════════════════════════════════════════════════════════════════════════
#  /PROGRESS COMMAND  (kept as shortcut — "/progress Bench Press")
# ═════════════════════════════════════════════════════════════════════════

async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a chart when the user types /progress <exercise>."""
    try:
        exercise = " ".join(context.args) if context.args else ""
        if not exercise:
            await update.message.reply_text(
                "⚠️ Please specify an exercise:\n"
                "`/progress Bench Press`\n\n"
                "Or use the *📊 View Progress* button.",
                parse_mode="Markdown",
                reply_markup=MAIN_MENU_KB,
            )
            return

        user = update.effective_user
        user_id = get_or_create_user(user.id, user.username)
        chart_buf = generate_progress_chart(user_id, exercise)

        if chart_buf is None:
            await update.message.reply_text(
                f"📭 No data found for *{exercise}*.",
                parse_mode="Markdown",
                reply_markup=MAIN_MENU_KB,
            )
            return

        await update.message.reply_photo(
            photo=chart_buf,
            caption=f"📈 Your progress for *{exercise.title()}*",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.error("Error in /progress: %s", exc, exc_info=True)
        await update.message.reply_text(
            "❌ Something went wrong while generating your chart.",
            reply_markup=MAIN_MENU_KB,
        )


# ═════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Load config, initialize the database, and start the bot."""
    # Fix for Python 3.14+ strict event loop rules
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token or token == "your-token-here":
        raise SystemExit(
            "ERROR: Set your TELEGRAM_BOT_TOKEN in the .env file.\n"
            "Get one from @BotFather on Telegram."
        )

    init_db()
    app = ApplicationBuilder().token(token).build()

    # ── Workout logging conversation ──────────────────────────────────
    log_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🏋️ Log Workout$"), log_workout_start),
        ],
        states={
            SELECT_MUSCLE: [
                CallbackQueryHandler(log_select_muscle, pattern=r"^log_mg:"),
            ],
            SELECT_EXERCISE: [
                CallbackQueryHandler(log_select_exercise, pattern=r"^log_ex:"),
            ],
            ENTER_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_enter_stats),
            ],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
        per_message=False,
    )

    # ── Progress viewing conversation ─────────────────────────────────
    progress_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📊 View Progress$"), progress_start),
        ],
        states={
            PROGRESS_MUSCLE: [
                CallbackQueryHandler(progress_select_muscle, pattern=r"^prog_mg:"),
            ],
            PROGRESS_EXERCISE: [
                CallbackQueryHandler(progress_select_exercise, pattern=r"^prog_ex:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
        per_message=False,
    )

    # ── Body weight conversation ──────────────────────────────────────
    body_weight_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^⚖️ Log Body Weight$"), body_weight_start),
        ],
        states={
            ENTER_BODY_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, body_weight_enter),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", log_cancel),
            # Prevent "📈 Weight Chart" from being consumed as weight input
            MessageHandler(filters.Regex("^📈 Weight Chart$"), weight_chart_fallback),
        ],
        per_message=False,
    )

    # Register handlers (order matters — conversations first)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(log_conv)
    app.add_handler(progress_conv)
    app.add_handler(body_weight_conv)
    app.add_handler(CommandHandler("progress", progress_command))

    # Undo button handler (standalone, outside conversations)
    app.add_handler(CallbackQueryHandler(handle_undo, pattern=r"^undo:"))

    # Weight chart button
    app.add_handler(MessageHandler(filters.Regex("^📈 Weight Chart$"), weight_chart_handler))

    # Fallback text workout parser
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_workout))

    # ── Decide: Webhook (Render) vs Polling (local) ───────────────────
    is_render = os.environ.get("RENDER", "").lower() == "true"

    if is_render:
        port = int(os.environ.get("PORT", 8443))
        url = os.environ.get("RENDER_EXTERNAL_URL", "")
        logger.info("🌐 Starting webhook on port %d → %s", port, url)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=url,
        )
    else:
        logger.info("🚀 Bot is running locally — press Ctrl+C to stop.")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
