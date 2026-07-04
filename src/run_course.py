"""Entry point: python -m src.run_course

Configure via environment (see .env.example). Defaults target OpenRouter's
free tier with a Qwen model. Also works with Groq or a local Ollama —
anything OpenAI-compatible.
"""

from .orchestrator import run_course

if __name__ == "__main__":
    run_course()
