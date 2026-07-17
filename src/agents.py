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
from pathlib import Path


def _load_dotenv() -> None:
    """Populate os.environ from <repo>/.env if present (real env vars win).

    Removes the 'forgot to export' footgun: `cp .env.example .env`, fill in
    the key, and `python3 -m src.run_course` just works — no export step.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.split(" #", 1)[0]  # tolerate inline comments: KEY=value  # note
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_dotenv()


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

# Fail fast with a human answer instead of an HTTP 401 mid-run.
_key_missing = API_KEY == "ollama" or "..." in API_KEY or "your_key_here" in API_KEY
if _key_missing and "localhost" not in BASE_URL and "127.0.0.1" not in BASE_URL:
    raise SystemExit(
        f"No API key found for {BASE_URL}.\n"
        "Fix: put your real key in .env (loaded automatically, no export step):\n"
        "  COURSE_API_KEY=<your key>\n"
        "Keys: OpenRouter https://openrouter.ai/keys · Groq https://console.groq.com\n"
        "      Qwen/DashScope https://modelstudio.console.alibabacloud.com (API-KEY page)\n"
        "(Using local Ollama? Set COURSE_BASE_URL=http://localhost:11434/v1.)"
    )
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
# Short-message design: agents text like humans, so completions are small.
# (Roomy enough for reasoning models that spend tokens on <think> blocks.)
MAX_TOKENS = int(os.environ.get("COURSE_MAX_TOKENS", "900"))
# Free tiers are rate-limited (OpenRouter free: ~20 req/min). Pause between calls.
SLEEP_BETWEEN_CALLS = float(os.environ.get("COURSE_SLEEP", "3.5"))
# Only the last N dialogue messages are sent per call. Long-term state lives in
# the mentor's memory block, so old turns are safely droppable — this bounds
# per-call prompt tokens (free tiers also cap tokens/day, not just requests).
HISTORY_WINDOW = int(os.environ.get("COURSE_HISTORY_WINDOW", "60"))

# Reasoning models (qwen3, deepseek-r1, gpt-oss...) emit chain-of-thought.
# Ask the provider to suppress it where supported; auto-disable on HTTP 400.
_extra_params: dict = {}
if "groq.com" in BASE_URL:
    _extra_params = {"reasoning_format": "hidden"}
elif "dashscope" in BASE_URL:  # Alibaba Cloud Model Studio (Qwen API)
    # Compatible-mode + non-streaming errors (or leaks) if thinking is on.
    _extra_params = {"enable_thinking": False}


def _strip_reasoning(text: str) -> str:
    """Remove chain-of-thought. Handles the nasty case: max_tokens cuts the
    completion before </think>, leaving UNCLOSED reasoning — in that case the
    whole output is thought, so we return '' and let the caller retry."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    elif "<think>" in text:
        return ""  # truncated mid-thought: nothing usable
    return text.strip()


def _chat_completion(messages: list[dict], max_tokens: int = MAX_TOKENS) -> tuple[str, int]:
    """One chat-completion call. Returns (text, http_status). Raises on hard errors.

    Uses plain urllib so the project runs with no third-party packages at all.
    """
    payload = {"model": MODELS[_active["idx"]], "max_tokens": max_tokens, "messages": messages}
    payload.update(_extra_params)
    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            # Some providers (e.g. Groq, behind Cloudflare) block the default
            # "Python-urllib/x.y" User-Agent as a bot signature.
            "User-Agent": "cmf-ai-task-2/1.0 (+https://github.com/egor-nak/cmf_ai_task_2)",
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
    def __init__(self, name: str, system_prompt: str, max_tokens: int = MAX_TOKENS):
        self.name = name
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens  # per-agent budget: student turns are tiny
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

        messages = [{"role": "system", "content": system}] + self.history[-HISTORY_WINDOW:]

        text = ""
        soft_fails = 0  # consecutive 429/5xx on the current model
        for attempt in range(10):
            time.sleep(SLEEP_BETWEEN_CALLS)
            try:
                text, status = _chat_completion(messages, self.max_tokens)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"[{self.name}] network error ({e}), retrying...")
                time.sleep(2**min(attempt, 4) * 5)
                continue
            if status == 200 and text:
                text = _strip_reasoning(text)
                if text:
                    break
                print(f"[{self.name}] output was all (truncated) reasoning — retrying")
                continue
            err, text = text, ""  # NEVER let an error body leak into the dialogue
            if status == 400 and _extra_params:
                # Provider rejected an optional param (e.g. reasoning_format on
                # a non-reasoning model) — drop extras and retry.
                print(f"[{self.name}] HTTP 400 with extra params {_extra_params} — retrying without")
                _extra_params.clear()
                continue
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

        self.history.append({"role": "assistant", "content": text})
        return text
