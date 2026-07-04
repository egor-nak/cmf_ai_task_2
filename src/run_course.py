"""Entry point: python -m src.run_course

Requires ANTHROPIC_API_KEY in the environment (see .env.example).
Optional: COURSE_MODEL to override the model (default claude-sonnet-4-5).
"""

from .orchestrator import run_course

if __name__ == "__main__":
    run_course()
