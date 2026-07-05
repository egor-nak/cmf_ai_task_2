"""Entry point.

Fresh run:   python3 -m src.run_course
Resume run:  python3 -m src.run_course --resume transcripts/run-YYYYMMDD-HHMMSS

Configure via environment (see .env.example). Defaults target OpenRouter's
free tier; also works with Groq or a local Ollama — anything OpenAI-compatible.
"""

import sys

from .orchestrator import run_course

if __name__ == "__main__":
    resume = None
    if "--resume" in sys.argv:
        i = sys.argv.index("--resume")
        if i + 1 >= len(sys.argv):
            sys.exit("usage: python3 -m src.run_course [--resume transcripts/run-<stamp>]")
        resume = sys.argv[i + 1].removesuffix(".jsonl").removesuffix(".md")
    run_course(resume=resume)
