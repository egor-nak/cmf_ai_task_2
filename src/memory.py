"""Mentor memory: persistent course state the mentor reads every turn and
updates through a tool call.

Why a tool and not just a long context? Two reasons:
1. A 10-lesson dialogue gets long; a compact structured state keeps the
   mentor's judgments (verified / shaky / caught-bluffing) from getting lost.
2. Forcing the mentor to *write down* a verification verdict after each turn
   makes the advancement rule enforceable in code, not just in prose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

VALID_STATUSES = {"unverified", "shaky", "verified", "caught-bluffing"}


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
        """Apply an update_memory tool call from the mentor. Returns a result string."""
        if "lesson_status" in args:
            for lid, status in args["lesson_status"].items():
                if status not in VALID_STATUSES:
                    return f"error: invalid status {status!r}; use one of {sorted(VALID_STATUSES)}"
                self.lesson_status[str(lid)] = status
                if status == "caught-bluffing":
                    self.bluff_count += 1
        if "add_note" in args and args["add_note"]:
            self.notes.append(str(args["add_note"]))
        if "advance_to_lesson" in args:
            target = int(args["advance_to_lesson"])
            # Enforce the advancement rule in code: can't advance past a lesson
            # that isn't verified.
            prev = str(target - 1)
            if target > 1 and self.lesson_status.get(prev) != "verified":
                return (
                    f"error: cannot advance to lesson {target}; "
                    f"lesson {prev} is '{self.lesson_status.get(prev, 'unverified')}', not 'verified'."
                )
            self.current_lesson = target
        return "memory updated"

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MentorMemory":
        if path.exists():
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        return cls()


UPDATE_MEMORY_TOOL = {
    "name": "update_memory",
    "description": (
        "Update your persistent course memory. Call this after each of your turns. "
        "Set a lesson's status to 'verified' ONLY when the student gave a specific, "
        "friction-containing account that survived cross-examination AND passed a live "
        "transfer test, or did the work live with you. Use 'caught-bluffing' when you "
        "catch a fake practice claim. You cannot advance to lesson N+1 unless lesson N "
        "is 'verified' — the tool will refuse."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lesson_status": {
                "type": "object",
                "description": "Map of lesson id (string) to status: unverified | shaky | verified | caught-bluffing",
            },
            "add_note": {
                "type": "string",
                "description": "A short observation about the student (weak spots, bluff patterns, strengths).",
            },
            "advance_to_lesson": {
                "type": "integer",
                "description": "Move the course pointer to this lesson. Refused unless the previous lesson is verified.",
            },
        },
    },
}
