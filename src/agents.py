"""Two-agent wrappers over any OpenAI-compatible chat API.

Works with free/cheap providers out of the box:
- OpenRouter (default): free-tier models like Qwen ':free' variants
- Groq: fast free tier (e.g. llama / qwen models)
- Ollama: fully free, local (base url http://localhost:11434/v1)

Zero required dependencies: uses the `openai` package if installed, otherwise
falls back to a built-in urllib client (same API surface, retries included).

Each agent keeps its OWN message history in which *it* is the assistant and
the other agent is the user — the cleanest way to run a symmetric dialogue.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request


def _make_ssl_context() -> ssl.SSLContext:
    """macOS python.org builds often lack root CAs (CERTIFICATE_VERIFY_FAILED).
    Prefer certifi's CA bundle when available; fall back to system default."""
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL_CTX = _make_ssl_context()

BASE_URL = os.environ.get("COURSE_BASE_URL", "https://openrouter.ai/api/v1")
API_KEY = (
    os.environ.get("COURSE_API_KEY")
    or os.environ.get("OPENROUTER_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or "ollama"  # Ollama ignores the key; anything non-empty works
)
MODEL = os.environ.get("COURSE_MODEL", "openai/gpt-oss-120b:free")
# Comma-separated fallbacks: free-tier models get saturated or lose :free status;
# the runner rotates to the next model on repeated 429s or on 404.
MODELS = [
    m.strip()
    for m in (MODEL + "," + os.environ.get("COURSE_FALLBACK_MODELS", "")).split(",")
    if m.strip()
]
_active = {"idx": 0}  # shared by both agents so they stay on the same model


def _rotate_model(reason: str) -> None:
    if _active["idx"] + 1 < len(MODELS):
        _active["idx"] += 1
        print(f"[models] {reason} — switching to {MODELS[_active['idx']]}")
    else:
        print(f"[models] {reason} — no fallbacks left, staying on {MODELS[_active['idx']]}")
MAX_TOKENS = int(os.environ.get("COURSE_MAX_TOKENS", "2400"))
# Free tiers are rate-limited (OpenRouter free: ~20 req/min). Pause between calls.
SLEEP_BETWEEN_CALLS = float(os.environ.get("COURSE_SLEEP", "3.5"))


def _chat_completion(messages: list[dict]) -> tuple[str, int]:
    """One chat-completion call. Returns (text, http_status). Raises on hard errors.

    Uses plain urllib so the project runs with no third-party packages at all.
    """
    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(
            {"model": MODELS[_active["idx"]], "max_tokens": MAX_TOKENS, "messages": messages}
        ).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180, context=_SSL_CTX) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.read().decode(errors="replace")[:500], e.code
    if "error" in data:  # OpenRouter sometimes returns 200 with an error body
        return json.dumps(data["error"])[:500], int(data["error"].get("code", 500) or 500)
    return (data["choices"][0]["message"].get("content") or "").strip(), 200


class Agent:
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.history: list[dict] = []  # this agent's own view of the dialogue

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
        soft_fails = 0  # consecutive 429/5xx on the current model
        for attempt in range(10):
            time.sleep(SLEEP_BETWEEN_CALLS)
            try:
                text, status = _chat_completion(messages)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"[{self.name}] network error ({e}), retrying...")
                time.sleep(2**min(attempt, 4) * 5)
                continue
            if status == 200 and text:
                break
            err, text = text, ""  # NEVER let an error body leak into the dialogue
            if status == 404:  # model lost :free status or was removed
                _rotate_model(f"HTTP 404 for {MODELS[_active['idx']]}")
                continue
            if status in (429, 500, 502, 503, 529):
                soft_fails += 1
                if soft_fails >= 2:  # saturated free pool — try the next model
                    _rotate_model(f"repeated HTTP {status} on {MODELS[_active['idx']]}")
                    soft_fails = 0
                    continue
                wait = 2**min(attempt, 3) * (10 if status == 429 else 5)
                print(f"[{self.name}] HTTP {status}, waiting {wait}s... ({err[:120]})")
                time.sleep(wait)
                continue
            if status == 200:
                continue  # empty completion: retry (flaky free endpoints)
            raise RuntimeError(f"{self.name}: HTTP {status}: {err[:300]}")
        if not text:
            raise RuntimeError(
                f"{self.name}: no completion after retries — quota likely exhausted "
                f"(tried: {', '.join(MODELS[: _active['idx'] + 1])}). "
                f"The run can be resumed later: python3 -m src.run_course --resume transcripts/run-<stamp>"
            )

        # Some free reasoning models emit <think>...</think>; strip it.
        if "<think>" in text and "</think>" in text:
            text = text.split("</think>", 1)[1].strip()

        self.history.append({"role": "assistant", "content": text})
        return text
