"""
keep_alive.py — Minimal web server to satisfy Render's port-binding requirement.

Render's free "Web Service" tier expects the app to bind to a port.
This lightweight aiohttp server runs alongside the Telegram bot to
prevent Render from killing the process.
"""

import os
from aiohttp import web


async def health_check(request: web.Request) -> web.Response:
    """Simple health-check endpoint."""
    return web.Response(text="🏋️ Workout Tracker Bot is alive!")


def start_keep_alive() -> None:
    """
    Start the aiohttp server in the background on the PORT env variable.
    Must be called from an already-running asyncio event loop (e.g. via
    Application.post_init).
    """
    app = web.Application()
    app.router.add_get("/", health_check)

    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)

    import asyncio

    async def _start():
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

    asyncio.get_event_loop().create_task(_start())
