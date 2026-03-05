"""
keep_alive.py — Flask-based dummy web server for Render deployment.

Render's free "Web Service" tier requires the app to bind to a port.
This Flask server runs in a background daemon thread so it doesn't
block the Telegram bot's main event loop.
"""

import os
from threading import Thread
from flask import Flask

app = Flask(__name__)


@app.route("/")
def health_check():
    """Simple health-check endpoint."""
    return "🏋️ Workout Tracker Bot is alive!", 200


def keep_alive():
    """Start the Flask server in a background daemon thread."""
    port = int(os.environ.get("PORT", 8080))
    thread = Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False),
        daemon=True,
    )
    thread.start()
