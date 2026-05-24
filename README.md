# LITHOVEX Telegram Bot

## Features
- Premium UI with inline buttons
- Normal chat mode for everyone
- Premium-only swarm mode
- Premium-only web research mode
- `/web <query>` live research command
- `/web on|off` web toggle for premium users
- Admin system
- SQLite memory
- Railway-ready worker deployment

## Commands
- /start
- /help
- /chat
- /swarm
- /web <query>
- /web on
- /web off
- /status
- /profile
- /agents
- /memory
- /clear
- /myid

Admin:
- /premium <user_id> on|off
- /role <user_id> normal|premium|admin
- /users

## Deploy
1. Copy `.env.example` to `.env`
2. Add your BOT_TOKEN
3. `pip install -r requirements.txt`
4. `python main.py`

## Railway
Use the included `Procfile`:
`worker: python main.py`
