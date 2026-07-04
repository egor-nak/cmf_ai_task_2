"""Two-agent wrappers over any OpenAI-compatible chat API.

Works with free/cheap providers out of the box:
- OpenRouter (default): free-tier models like Qwen ':free' variants
- Groq: fast free tier (e.g. llama / qwen models)
- Ollama: fully free, local (base url http://localhost:11434/v1)

Each agent keeps its OWN message history in which *it* is the assistant and
the other agent is the user — the cleanest way to run a symmetric dialogue.
"""

from __future__ import annotations

import os
import time

from openai import OpenAI, APIStatusError, RateLimitError

BASE_URL = os.environ.get("COURSE_BASE_URL", "https://openrouter.ai/api/v1")
API_KEY = (
    os.environ.get("COURSE_API_KEY")
    or os.environ.get("OPENROUTER_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or "ollama"  # Ollama ignores the key; anything non-empty works
)
MODEL = os.environ.get("COURSE_MODEL", "qwen/qwen3-14b:free")
MAX_TOKENS = int(os.environ.get("COURSE_MAX_TOKENS", "1200"))
# Free tiers are rate-limited (OpenRouter free: ~20 req/min). Pause between calls.
SLEEP_BETWEEN_CALLS = float(os.environ.get("COURSE_SLEEP", "3.5"))


class Agent:
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.history: list[dict] = []  # this agent's own view of the dialogue
        self.client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    def hear(self, text: str) -> None:
        """Record a message from the other agent (as 'user' in this agent's view)."""
        self.history.append({"role": "user", "content": text})

    def speak(self, memory_block: str | None = None) -> str:
        """Produce this agent's next turn."""
        system = self.system_prompt
        if memory_block:
            # Memory goes into system context each turn so it never scrolls away.
            system = f"{self.system_prompt}\n\n{memory_block}"

        messages = [{"role": "system", "content": system}] + self.history

        text = ""
        for attempt in range(6):
            try:
                time.sleep(SLEEP_BETWEEN_CALLS)
                response = self.client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    messages=messages,
                )
                text = (response.choices[0].message.content or "").strip()
                # Some free reasoning models emit <think>...</think>; strip it.
                if "<think>" in text and "</think>" in text:
                    text = text.split("</think>", 1)[1].strip()
                if text:
                    break
                # Empty completion: retry (happens on flaky free endpoints).
            except RateLimitError:
                wait = 2**attempt * 5
                print(f"[{self.name}] rate limited, waiting {wait}s...")
                time.sleep(wait)
            except APIStatusError as e:
                if e.status_code in (429, 500, 502, 503, 529) and attempt < 5:
                    time.sleep(2**attempt * 5)
                    continue
                raise
        if not text:
            raise RuntimeError(f"{self.name}: no completion after retries (model={MODEL})")

        self.history.append({"role": "assistant", "content": text})
        return text
