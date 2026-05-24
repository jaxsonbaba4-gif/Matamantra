from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from config import SETTINGS

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
}

class LithovexClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session: aiohttp.ClientSession | None = None

    async def open(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180))

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        use_web_search: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        await self.open()
        assert self.session is not None

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 2048,
            "stream": stream,
            "use_web_search": use_web_search,
            "project_context": "",
        }

        headers = dict(HEADERS)
        if extra_headers:
            headers.update(extra_headers)

        url = f"{self.base_url}/api/chat/completions"

        async with self.session.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")

            if not stream:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    return text.strip()

                if isinstance(data, dict):
                    if "choices" in data and data["choices"]:
                        choice0 = data["choices"][0]
                        if isinstance(choice0, dict):
                            if "message" in choice0 and isinstance(choice0["message"], dict):
                                content = choice0["message"].get("content")
                                if content:
                                    return content
                            if "delta" in choice0 and isinstance(choice0["delta"], dict):
                                content = choice0["delta"].get("content")
                                if content:
                                    return content
                    for key in ("content", "response", "text", "answer"):
                        if key in data and isinstance(data[key], str):
                            return data[key]
                return text.strip()

            chunks: list[str] = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    data = json.loads(line)
                    chunk = ""
                    if "choices" in data and data["choices"]:
                        choice0 = data["choices"][0]
                        if isinstance(choice0, dict):
                            chunk = choice0.get("delta", {}).get("content", "") or choice0.get("message", {}).get("content", "")
                    elif "content" in data:
                        chunk = data["content"]
                    elif "text" in data:
                        chunk = data["text"]
                    if chunk:
                        chunks.append(chunk)
                except Exception:
                    chunks.append(line)
            return "".join(chunks).strip()

CLIENT = LithovexClient(SETTINGS.base_url)

async def run_single_chat(user_text: str, history: list[dict[str, str]], *, use_web_search: bool = False) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a polished, helpful Telegram assistant. "
                "Be concise, warm, and useful. "
                "Never mention internal routing, models, or hidden system details."
            ),
        }
    ]
    messages.extend(history[-SETTINGS.max_history_messages:])
    messages.append({"role": "user", "content": user_text})
    return await CLIENT.chat_completion(
        SETTINGS.default_model,
        messages,
        stream=False,
        use_web_search=use_web_search,
    )

async def _agent_call(model: str, system_prompt: str, user_text: str, history: list[dict[str, str]], *, use_web_search: bool = False) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-6:],
        {"role": "user", "content": user_text},
    ]
    return await CLIENT.chat_completion(
        model,
        messages,
        stream=False,
        use_web_search=use_web_search,
        extra_headers={"x-swarm-mode": "true"},
    )

async def run_swarm(user_text: str, history: list[dict[str, str]], *, use_web_search: bool = False) -> str:
    prompts = {
        "researcher": "You are an expert researcher. Gather relevant facts, examples, and evidence. Stay on the user's topic only. Keep it compact but specific.",
        "analyst": "You are a sharp analyst. Apply structured reasoning, frameworks, and comparison. Stay tightly focused on the user's topic.",
        "planner": "You are a practical planner. Turn the task into clear steps, milestones, and actions.",
        "writer": "You are a polished writer. Produce natural, ready-to-use wording with good tone.",
        "critic": "You are a critic. Stress test the idea, identify risks, edge cases, and weak points.",
        "implementer": "You are a systems implementer. Focus on execution, tooling, workflow, and practical setup.",
    }

    models = {
        "researcher": SETTINGS.swarm_researcher_model,
        "analyst": SETTINGS.swarm_analyst_model,
        "planner": SETTINGS.swarm_planner_model,
        "writer": SETTINGS.swarm_writer_model,
        "critic": SETTINGS.swarm_analyst_model,
        "implementer": SETTINGS.swarm_implementer_model,
    }

    async def one(role: str) -> tuple[str, str]:
        try:
            result = await _agent_call(
                models[role],
                prompts[role],
                user_text,
                history,
                use_web_search=use_web_search and role == "researcher",
            )
            return role, result
        except Exception as exc:
            return role, f"[{role} error] {exc}"

    results = await asyncio.gather(*(one(role) for role in prompts))

    agent_blob = []
    for role, content in results:
        agent_blob.append(f"## {role.upper()}\n{content}")

    synthesis_prompt = (
        "You are a premium synthesis engine. "
        "Combine the agent outputs into one cohesive answer. "
        "Be polished, concise, and directly useful. "
        "If web research was used, preserve the useful facts clearly."
    )

    synthesis_user = (
        f"User request:\n{user_text}\n\n"
        f"Recent chat history:\n{json.dumps(history[-6:], ensure_ascii=False, indent=2)}\n\n"
        f"Agent outputs:\n\n" + "\n\n".join(agent_blob)
    )

    try:
        final = await CLIENT.chat_completion(
            SETTINGS.swarm_synthesis_model,
            [
                {"role": "system", "content": synthesis_prompt},
                {"role": "user", "content": synthesis_user},
            ],
            stream=False,
            use_web_search=use_web_search,
            extra_headers={"x-swarm-mode": "true"},
        )
    except Exception:
        final = "\n\n".join(agent_blob)

    return final

async def web_research(query: str, history: list[dict[str, str]]) -> str:
    system = (
        "You are a live web research assistant. "
        "Use the web search tool if available. "
        "Return concise, factual, well-structured research. "
        "If uncertain, say so explicitly."
    )
    messages = [
        {"role": "system", "content": system},
        *history[-4:],
        {"role": "user", "content": query},
    ]
    return await CLIENT.chat_completion(
        SETTINGS.web_research_model,
        messages,
        stream=False,
        use_web_search=True,
        extra_headers={"x-swarm-mode": "true"},
    )
