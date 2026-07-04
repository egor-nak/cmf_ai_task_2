"""Orchestrates the mentor-student conversation across the full course.

Loop shape:
    mentor speaks -> student hears -> student speaks -> mentor hears -> repeat

The mentor drives: it decides when a lesson is verified and calls
update_memory(advance_to_lesson=N). The loop ends when the mentor's memory
points past the last lesson and it has delivered a final assessment, or when
the turn budget runs out (safety valve).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .agents import Agent, MODEL
from .memory import MentorMemory, UPDATE_MEMORY_TOOL

ROOT = Path(__file__).resolve().parent.parent
MAX_TURN_PAIRS = 140  # hard safety cap for the whole course
COMPLETE_MARK = "[COURSE_COMPLETE]"


def load_text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def build_mentor_system() -> str:
    prompt = load_text("prompts/mentor_system.md")
    curriculum = load_text("course/curriculum.json")
    return (
        f"{prompt}\n\n## Curriculum (teach these lessons in order)\n"
        f"```json\n{curriculum}\n```\n\n"
        f"When the final assessment after lesson 10 is delivered, end your last "
        f"message with the exact marker {COMPLETE_MARK}."
    )


def run_course(out_dir: Path | None = None) -> Path:
    out_dir = out_dir or (ROOT / "transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    md_path = out_dir / f"run-{stamp}.md"
    jsonl_path = out_dir / f"run-{stamp}.jsonl"
    memory_path = out_dir / f"run-{stamp}-memory.json"

    memory = MentorMemory()
    mentor = Agent("Maya (mentor)", build_mentor_system(), tools=[UPDATE_MEMORY_TOOL])
    student = Agent("Denis (student)", load_text("prompts/student_system.md"))

    def handle_mentor_tool(name: str, args: dict) -> str:
        if name == "update_memory":
            result = memory.apply_update(args)
            memory.save(memory_path)
            return result
        return f"error: unknown tool {name}"

    transcript: list[dict] = []

    def record(speaker: str, text: str) -> None:
        transcript.append({"speaker": speaker, "lesson": memory.current_lesson, "text": text})
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(transcript[-1], ensure_ascii=False) + "\n")
        print(f"\n----- {speaker} (lesson {memory.current_lesson}) -----\n{text}")

    # Kick off: the mentor opens the course.
    mentor.hear("(The student has joined the chat. Begin the course.)")

    for _ in range(MAX_TURN_PAIRS):
        mentor_text = mentor.speak(memory_block=memory.to_block(), tool_handler=handle_mentor_tool)
        record("Maya (mentor)", mentor_text)
        if COMPLETE_MARK in mentor_text:
            break
        student.hear(mentor_text.replace(COMPLETE_MARK, "").strip())

        student_text = student.speak()
        record("Denis (student)", student_text)
        mentor.hear(student_text)

    # Write the markdown transcript.
    lines = [
        "# Course transcript",
        f"Model: {MODEL} · Turn pairs: {len(transcript) // 2} · Bluffs caught: {memory.bluff_count}",
        "",
    ]
    for entry in transcript:
        lines.append(f"**{entry['speaker']}** *(lesson {entry['lesson']})*")
        lines.append("")
        lines.append(entry["text"])
        lines.append("")
        lines.append("---")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    memory.save(memory_path)
    print(f"\nDone. Transcript: {md_path}\nMemory: {memory_path}")
    return md_path
