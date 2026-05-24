from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiohttp

from config import Settings


@dataclass(frozen=True)
class AgentSpec:
    name: str
    model: str
    system_prompt: str


AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="Researcher",
        model="meta-llama/Llama-3.3-70B-Instruct",
        system_prompt=(
            "You are an expert researcher. Gather facts, examples, evidence, and relevant context "
            "for the user's task. Stay specific and avoid generic filler."
        ),
    ),
    AgentSpec(
        name="Analyst",
        model="Qwen/Qwen2.5-72B-Instruct",
        system_prompt=(
            "You are a senior analyst. Apply structured reasoning, frameworks, comparisons, and "
            "trade-offs directly to the user's task."
        ),
    ),
    AgentSpec(
        name="Implementer",
        model="Qwen/Qwen2.5-Coder-32B-Instruct",
        system_prompt=(
            "You are a technical systems expert. If code or tooling is relevant, provide clean "
            "implementation thinking. Otherwise, explain the operational flow and system design."
        ),
    ),
    AgentSpec(
        name="Critic",
        model="meta-llama/Llama-3.3-70B-Instruct",
        system_prompt=(
            "You are a critical reviewer. Stress-test the task, identify risks, edge cases, blind "
            "spots, and what could go wrong."
        ),
    ),
    AgentSpec(
        name="Planner",
        model="mistralai/Mistral-Large-Instruct-2411",
        system_prompt=(
            "You are a strategic planner. Create a concrete step-by-step plan with milestones, "
            "timelines, and success criteria."
        ),
    ),
    AgentSpec(
        name="Writer",
        model="Qwen/QwQ-32B",
        system_prompt=(
            "You are a polished writer. Produce a clean, ready-to-use response that directly "
            "addresses the user's task."
        ),
    ),
]


class LithovexClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "LithovexClient":
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("HTTP session not initialized.")
        return self._session

    async def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1200,
        stream: bool = False,
        use_web_search: bool = False,
        project_context: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        url = f"{self.settings.base_url}/api/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
            "use_web_search": use_web_search,
            "project_context": project_context,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TelegramSwarmBot/1.0",
        }
        if extra_headers:
            headers.update(extra_headers)

        async with self.session.post(url, json=payload, headers=headers) as resp:
            body = await resp.text()

            if resp.status >= 400:
                raise RuntimeError(f"{resp.status} from {url}: {body[:700]}")

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type or body.lstrip().startswith("{"):
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    return body.strip()
                return extract_content(data)

            return body.strip()

    async def direct_reply(
        self,
        user_text: str,
        history: list[dict[str, str]],
        use_web_search: bool,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful Telegram assistant. Be concise, natural, and accurate. "
                    "Use the conversation history when helpful."
                ),
            },
            *history,
            {"role": "user", "content": user_text},
        ]
        return await self.chat_completions(
            model=self.settings.direct_model,
            messages=messages,
            max_tokens=1200,
            use_web_search=use_web_search,
        )

    async def run_swarm(
        self,
        user_text: str,
        history: list[dict[str, str]],
        use_web_search: bool,
    ) -> tuple[str, dict[str, str]]:
        tasks = [
            self._run_agent(agent, user_text, history, use_web_search)
            for agent in AGENTS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs: dict[str, str] = {}
        for agent, result in zip(AGENTS, results):
            if isinstance(result, Exception):
                outputs[agent.name] = f"ERROR: {result}"
            else:
                outputs[agent.name] = result

        synthesis_input = build_synthesis_prompt(user_text, history, outputs)
        synthesis_messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert synthesis engine. Merge multiple specialist viewpoints into "
                    "one coherent answer. Avoid repetition. Be natural and useful."
                ),
            },
            {"role": "user", "content": synthesis_input},
        ]
        final = await self.chat_completions(
            model=self.settings.synthesis_model,
            messages=synthesis_messages,
            max_tokens=1600,
            use_web_search=use_web_search,
        )

        return final, outputs

    async def _run_agent(
        self,
        agent: AgentSpec,
        user_text: str,
        history: list[dict[str, str]],
        use_web_search: bool,
    ) -> str:
        messages = [
            {"role": "system", "content": agent.system_prompt},
            *history,
            {"role": "user", "content": user_text},
        ]
        return await self.chat_completions(
            model=agent.model,
            messages=messages,
            max_tokens=1000,
            use_web_search=use_web_search,
        )


def extract_content(data: Any) -> str:
    if isinstance(data, str):
        return data.strip()

    if isinstance(data, dict):
        if "choices" in data and data["choices"]:
            choice = data["choices"][0]
            if isinstance(choice, dict):
                if isinstance(choice.get("message"), dict):
                    content = choice["message"].get("content")
                    if content is not None:
                        return str(content).strip()
                if isinstance(choice.get("delta"), dict):
                    content = choice["delta"].get("content")
                    if content is not None:
                        return str(content).strip()
        for key in ("content", "text", "response", "output"):
            if key in data and data[key] is not None:
                return str(data[key]).strip()
        return json.dumps(data, ensure_ascii=False)

    return str(data).strip()


def build_synthesis_prompt(
    user_text: str,
    history: list[dict[str, str]],
    outputs: dict[str, str],
) -> str:
    history_block = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in history[-6:]
    ) or "(no prior history)"

    agent_block = "\n\n".join(
        f"### {name}\n{content}" for name, content in outputs.items()
    )

    return (
        "Combine these outputs into one final answer for the user.\n\n"
        f"User request:\n{user_text}\n\n"
        f"Recent conversation history:\n{history_block}\n\n"
        f"Agent outputs:\n{agent_block}\n\n"
        "Return only the final answer, with no commentary about the process."
    )


def should_use_swarm(mode: str, user_text: str) -> bool:
    mode = mode.lower().strip()
    if mode == "swarm":
        return True
    if mode in {"fast", "chat"}:
        return False
    keywords = ("how", "why", "analyze", "compare", "plan", "build", "research", "design", "explain")
    return len(user_text.split()) >= 8 or any(k in user_text.lower() for k in keywords)
