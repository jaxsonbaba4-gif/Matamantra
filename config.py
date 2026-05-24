from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

def _csv(value: str) -> list[str]:
    return [x.strip().lstrip("@") for x in (value or "").split(",") if x.strip()]

@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "").strip()
    base_url: str = os.getenv("BASE_URL", "https://lithovex.up.railway.app").rstrip("/")
    db_path: str = os.getenv("DB_PATH", "bot.db").strip()
    admin_usernames: list[str] = field(default_factory=lambda: _csv(os.getenv("ADMIN_USERNAMES", "")))
    default_model: str = os.getenv("DEFAULT_MODEL", "lithovex-2.5-core").strip()
    swarm_researcher_model: str = os.getenv("SWARM_RESEARCHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct").strip()
    swarm_analyst_model: str = os.getenv("SWARM_ANALYST_MODEL", "Qwen/Qwen2.5-72B-Instruct").strip()
    swarm_planner_model: str = os.getenv("SWARM_PLANNER_MODEL", "mistralai/Mistral-Large-Instruct-2411").strip()
    swarm_writer_model: str = os.getenv("SWARM_WRITER_MODEL", "Qwen/QwQ-32B").strip()
    swarm_implementer_model: str = os.getenv("SWARM_IMPLEMENTER_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct").strip()
    swarm_synthesis_model: str = os.getenv("SWARM_SYNTHESIS_MODEL", "meta-llama/Llama-3.3-70B-Instruct").strip()
    web_research_model: str = os.getenv("WEB_RESEARCH_MODEL", "meta-llama/Llama-3.3-70B-Instruct").strip()
    max_history_messages: int = 12

SETTINGS = Settings()
