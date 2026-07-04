"""Mentor memory: persistent course state the mentor reads every turn and
updates through a structured text block.

Why a text protocol instead of native tool calling? The runner targets cheap /
free models (OpenRouter :free tier, Groq, local Ollama), where function-calling
support is inconsistent or absent. A fenced <memory>{json}</memory> block at
the end of the mentor's message works on ANY chat model, and the orchestrator
still enforces the advancement rule in code: an invalid advance is refused and
the error is fed back to the mentor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

VALID_STATUSES = {"unverified", "shaky", "verified", "caught-bluffing"}

MEMORY_BLOCK_RE = re.compile(r"<memory>\s*(\{.*?\})\s*</memory>", re.DOTALL)

MEMORY_PROTOCOL = """
## Memory protocol (machine-read — follow exactly)
End EVERY message with a memory update on its own line, in this exact form:

<memory>{"lesson_status": {"<lesson id>": "<unverified|shaky|verified|caught-bluffing>"}, "add_note": "<short observation or empty>", "advance_to_lesson": <current or next lesson number>}</memory>

Rules:
- Set a lesson to "verified" ONLY when the student gave a specific, friction-containing account that survived cross-examination AND passed a live transfer test, or did the work live with you.
- Use "caught-bluffing" the moment you catch a fake practice claim.
- You cannot advance to lesson N+1 unless lesson N is "verified" — the system will refuse and tell you.
- The student never sees this block. Everything before it is your normal message.
"""


@dataclass
class MentorMemory:
    current_lesson: int = 1
    lesson_status: dict[str, str] = field(default_factory=dict)  # lesson id -> status
    notes: list[str] = field(default_factory=list)  # mentor's own observations
    bluff_count: int = 0

    def to_block(self) -> str:
        """Render as the MEMORY block injected before every mentor turn."""
        lines = [
            "=== MEMORY (course state — trust this over your recollection) ===",
            f"Current lesson: {self.current_lesson}",
            f"Bluffs caught so far: {self.bluff_count}",
            "Lesson verification status:",
        ]
        for lid in sorted(self.lesson_status, key=int):
            lines.append(f"  Lesson {lid}: {self.lesson_status[lid]}")
        if self.notes:
            lines.append("Your notes on the student:")
            lines.extend(f"  - {n}" for n in self.notes[-12:])  # keep it compact
        lines.append("=== END MEMORY ===")
        return "\n".join(lines)

    def apply_update(self, args: dict) -> str:
        """Apply a parsed <memory> update. Returns 'memory updated' or an error string."""
        if "lesson_status" in args and isinstance(args["lesson_status"], dict):
            for lid, status in args["lesson_status"].items():
                if status not in VALID_STATUSES:
                    return f"error: invalid status {status!r}; use one of {sorted(VALID_STATUSES)}"
                already_caught = self.lesson_status.get(str(lid)) == "caught-bluffing"
                self.lesson_status[str(lid)] = status
                if status == "caught-bluffing" and not already_caught:
                    self.bluff_count += 1
        note = args.get("add_note")
        if note:
            self.notes.append(str(note))
        if "advance_to_lesson" in args:
            try:
                target = int(args["advance_to_lesson"])
            except (TypeError, ValueError):
                return "error: advance_to_lesson must be an integer"
            prev = str(target - 1)
            # Enforce the advancement rule in code.
            if target > self.current_lesson and self.lesson_status.get(prev) != "verified":
                return (
                    f"error: cannot advance to lesson {target}; "
                    f"lesson {prev} is '{self.lesson_status.get(prev, 'unverified')}', not 'verified'."
                )
            if target >= self.current_lesson:  # never move backwards silently
                self.current_lesson = target
        return "memory updated"

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MentorMemory":
        if path.exists():
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        return cls()


def extract_memory_update(text: str) -> tuple[str, dict | None, str | None]:
    """Split mentor output into (visible_text, parsed_update_or_None, parse_error).

    Tolerant on purpose: free models mangle formats sometimes. If the block is
    missing or unparseable we return the text unchanged and report the problem
    so the orchestrator can nudge the mentor next turn.
    """
    m = MEMORY_BLOCK_RE.search(text)
    if not m:
        return text.strip(), None, "no <memory> block found"
    visible = (text[: m.start()] + text[m.end() :]).strip()
    try:
        return visible, json.loads(m.group(1)), None
    except json.JSONDecodeError as e:
        return visible, None, f"unparseable <memory> JSON: {e}"
