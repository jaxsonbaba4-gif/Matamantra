from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    base_url: str = "https://lithovex.up.railway.app"
    db_path: str = "bot.db"
    request_timeout: int = 120
    max_history_turns: int = 8
    direct_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    synthesis_model: str = "meta-llama/Llama-3.3-70B-Instruct"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Add it to your .env or Railway variables.")

    return Settings(
        bot_token=token,
        base_url=os.getenv("BASE_URL", "https://lithovex.up.railway.app").rstrip("/"),
        db_path=os.getenv("DB_PATH", "bot.db"),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "120")),
        max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "8")),
        direct_model=os.getenv("DIRECT_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        synthesis_model=os.getenv("SYNTHESIS_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
    )
