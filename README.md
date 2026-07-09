# 🏋️ RepRecord

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-v21.10-0088cc.svg?logo=telegram)](https://core.telegram.org/bots/api)
[![Database](https://img.shields.io/badge/Database-PostgreSQL-336791.svg?logo=postgresql)](https://www.postgresql.org/)
[![Visualization](https://img.shields.io/badge/Visualization-Matplotlib%20%26%20Pandas-orange.svg?logo=python)](https://matplotlib.org/)

**RepRecord** is a highly interactive, dark-themed personal workout and body weight tracking Telegram bot. Built with `python-telegram-bot`, `pandas`, `matplotlib`, and `psycopg2`, it enables fitness enthusiasts to log workouts, track progressive overload, monitor body weight trends, and view detailed progress charts directly inside Telegram.

---

## 📸 Visual Highlights

RepRecord includes a thread-safe, custom dark-themed visualization engine that renders beautiful charts.

| 📈 Strength & Progressive Overload | ⚖️ Body Weight Progression |
| :---: | :---: |
| ![Workout Progress](assets/workout_progress.png) | ![Weight Progress](assets/weight_progress.png) |

---

## ✨ Features

- ⌨️ **Persistent Bottom Keyboard**: Access core functions instantly with the custom bottom menu (`🏋️ Log Workout`, `📊 View Progress`, `⚖️ Log Body Weight`, `📈 Weight Chart`).
- 🤖 **Interactive Logging Flow**: Guided inline keyboards for selecting muscle groups and specific exercises.
- 💡 **Smart Reminders**: Displays your previous stats (sets × reps @ weight) when starting an exercise log to keep you motivated to beat your personal best.
- 📉 **Auto-Generated Dark Charts**: Interactive inline button picker generates high-DPI trend charts with progressive overload stats, min/max metrics, and custom annotations.
- ❌ **Instant Undo Action**: Accidentally logged the wrong numbers? Tap the inline "Undo Last Entry" button to instantly wipe the last database record.
- ✍️ **Flexible Free-text Parser**: Skip the menus and type directly: `Incline Chest Press 4x10 60kg` to log workouts in one message.
- 🔒 **Cloud Ready**: Auto-enforces SSL connections for PostgreSQL providers (e.g. Supabase, Render) and integrates with environment configurations.
- 🌐 **Adaptive Deployment**: Seamlessly switches between local execution (Polling) and production deployment (Webhooks on Render).

---

## 🏗️ System Architecture

The following diagram illustrates the workflow and interaction between the Telegram API, the bot application, the PostgreSQL database, and the Matplotlib visualization engine:

```mermaid
graph TD
    User([User on Telegram]) <-->|Message / Callback| TelegramAPI[Telegram API]
    TelegramAPI <-->|Webhook / Polling| Bot[main.py Bot Core]
    Bot -->|CRUD Operations| DB[(PostgreSQL Database)]
    Bot -->|Request Chart| Vis[visualize.py Chart Engine]
    Vis -->|Read Data| DB
    Vis -->|Matplotlib / Pandas Agg| ChartBytes[PNG Bytes]
    ChartBytes -->|Send Photo| TelegramAPI
```

---

## 🗄️ Database Schema

RepRecord uses a normalized PostgreSQL relational database. The schema consists of three core tables:

```mermaid
erDiagram
    USERS {
        int id PK "SERIAL"
        bigint telegram_id UK "Telegram User ID"
        text username "Telegram Username"
        text created_at "ISO Timestamp"
    }
    WORKOUTS {
        int id PK "SERIAL"
        int user_id FK "References users.id"
        text date "YYYY-MM-DD"
        text exercise_name "Name of Exercise"
        int sets "Number of Sets"
        int reps "Number of Reps"
        real weight_kg "Weight in kg"
    }
    BODY_WEIGHT {
        int id PK "SERIAL"
        int user_id FK "References users.id"
        text date "YYYY-MM-DD"
        real weight_kg "Weight in kg"
    }
    USERS ||--o{ WORKOUTS : "logs"
    USERS ||--o{ BODY_WEIGHT : "tracks"
```

---

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/FaridMahmudlu/RepRecord.git
cd RepRecord
```

### 2. Install Dependencies
It is recommended to use a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure the Environment
Create a `.env` file in the root directory (based on `.env.example` if available, or write directly):
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://username:password@host:port/database
# For Webhook deployment (optional):
RENDER=false
PORT=8443
RENDER_EXTERNAL_URL=https://your-app-name.onrender.com
```

> [!TIP]
> Get a bot token from [@BotFather](https://t.me/BotFather) on Telegram.
> You can use a free PostgreSQL database hosted on [Supabase](https://supabase.com) or [Neon](https://neon.tech).

---

## 🚀 Running the Bot

### Locally (Polling Mode)
Run the application directly:
```bash
python main.py
```

### Production (Webhook Mode on Render)
RepRecord supports automatic webhook routing. Set the environment variable `RENDER=true` and configure the service port. The bot will automatically start a server listening for Telegram webhook events.

---

## 📂 Project Structure

```
RepRecord/
├── assets/                  # Pre-rendered chart examples for documentation
│   ├── workout_progress.png
│   └── weight_progress.png
├── database.py              # PostgreSQL database CRUD operations and connection logic
├── main.py                  # Bot handlers, interactive menus, state machines, and main entrypoint
├── requirements.txt         # Project dependencies
├── visualize.py             # Thread-safe chart rendering engine (non-interactive matplotlib)
└── .env                     # Local configuration and secret keys (ignored by git)
```

---

## 🛠️ Built With

- **[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)** - Framework for building Telegram bots
- **[Matplotlib](https://matplotlib.org/)** - Static chart rendering engine (Agg backend)
- **[Pandas](https://pandas.pydata.org/)** - Data manipulation and preparation
- **[Psycopg2](https://www.psycopg.org/)** - PostgreSQL database adapter for Python

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information (if applicable).
