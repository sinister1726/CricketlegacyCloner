# Nexora Cricket Bot

A Telegram bot for cricket-based group games with a Flask web log dashboard.

## Architecture

- **bot.py** - Main Telegram bot entry point using Pyrogram/Pyrofork
- **app.py** - Flask web dashboard for live log monitoring (runs on port 5000)
- **plugins/** - Modular bot plugins (game, admin, common, utilities)
  - **plugins/game/duel.py** - 1v1 DM-based duel mode with matchmaking queue
  - **plugins/utilities/nudge.py** - Inactivity nudge background task
- **database/** - MongoDB database layer using motor (async)
- **utils/** - Shared utility functions
- **config.py** - Centralized configuration (API keys, DB URL, bot settings)
- **Assets/** - Static resources (fonts, images for scorecards)

## Key Features

- Team/Solo game modes in groups
- **1v1 Duel mode** — button-only DM cricket, matchmaking queue with 2-min timeout
- Form tracker — last 5 match results shown on profile (🟢🔴)
- Personality button on profile — shows Cricket DNA by editing caption
- 1v1 Stats button on profile — separate duel leaderboard
- Inactivity nudge — DMs players after 3+ days idle
- Career stats, rank tiers, achievements, best partnership tracking
- **Solo timeout 2-strike ban system** — 2 consecutive misses → -6 runs penalty, elimination, 20-min ban
- **Event/Tournament system** — `/start_event`, `/register`, `/deregister`, `/list_events`, `/event_players`, `/end_event`
- **Broadcast upgrade** — `/broadcast` now offers Forward (with label) or Copy (clean, no label) modes via inline buttons

## Technologies

- **Language:** Python 3.12
- **Telegram Framework:** Pyrofork (Pyrogram fork)
- **Database:** MongoDB Atlas via motor (async)
- **Web Dashboard:** Flask + Gunicorn
- **Image Processing:** Pillow, matplotlib

## Running

The app runs both processes together:
- Gunicorn serves the Flask dashboard on `0.0.0.0:5000`
- `python3 bot.py` runs the Telegram bot

```
gunicorn --bind 0.0.0.0:5000 app:app & python3 bot.py
```

## Deployment

Deployed as a VM (always-running) deployment to keep the Telegram bot alive continuously.

## Configuration

All configuration is in `config.py`:
- `API_ID`, `API_HASH`, `BOT_TOKEN` - Telegram credentials
- `MONGO_URL` - MongoDB Atlas connection string
- `asyncpg` - also installed for `/transfer` command (PostgreSQL → MongoDB data migration)
- `OWNER_IDS` - Bot owner Telegram user IDs
- `LOG_CHANNEL` - Telegram channel ID for startup logs
