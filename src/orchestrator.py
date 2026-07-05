"""Orchestrates the mentor-student conversation across the full course.

Loop shape:
    mentor speaks -> memory block parsed & applied -> student hears visible text
    -> student speaks -> mentor hears -> repeat

The mentor drives: it emits a <memory>{...}</memory> block each turn (see
src/memory.py). The orchestrator enforces the advancement rule in code — an
invalid advance or a malformed block produces a corrective note the mentor
sees on its next turn. The loop ends when the mentor prints [COURSE_COMPLETE]
after the final assessment, or when the turn budget runs out (safety valve).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .agents import Agent, MODEL
from .memory import (
    MEMORY_PROTOCOL,
    MentorMemory,
    extract_memory_update,
    scrub_memory_blocks,
)

ROOT = Path(__file__).resolve().parent.parent
MAX_TURN_PAIRS = 140  # hard safety cap for the whole course
COMPLETE_MARK = "[COURSE_COMPLETE]"


def load_text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def build_mentor_system() -> str:
    prompt = load_text("prompts/mentor_system.md")
    curriculum = load_text("course/curriculum.json")
    return (
        f"{prompt}\n{MEMORY_PROTOCOL}\n"
        f"## Curriculum (teach these lessons in order)\n"
        f"```json\n{curriculum}\n```\n\n"
        f"When the final assessment after lesson 10 is delivered, end your last "
        f"message (before the memory block) with the exact marker {COMPLETE_MARK}."
    )


def run_course(out_dir: Path | None = None, resume: str | None = None) -> Path:
    """Run the course. `resume` is a path prefix of an interrupted run, e.g.
    'transcripts/run-20260705-190000' — histories are rebuilt from its .jsonl
    and memory from its -memory.json, and the course continues from there."""
    out_dir = out_dir or (ROOT / "transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)

    if resume:
        prefix = Path(resume)
        if not prefix.is_absolute():
            prefix = ROOT / prefix
        stamp = prefix.name.replace("run-", "")
        out_dir = prefix.parent
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
    md_path = out_dir / f"run-{stamp}.md"
    jsonl_path = out_dir / f"run-{stamp}.jsonl"
    memory_path = out_dir / f"run-{stamp}-memory.json"

    memory = MentorMemory.load(memory_path) if resume else MentorMemory()
    mentor = Agent("Maya (mentor)", build_mentor_system())
    student = Agent("Denis (student)", load_text("prompts/student_system.md"))

    transcript: list[dict] = []

    if resume:
        # Rebuild both agents' histories from the interrupted run's transcript.
        entries = [
            json.loads(line)
            for line in jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        mentor.hear("(The student has joined the chat. Begin the course.)")
        for e in entries:
            text = scrub_memory_blocks(e["text"])
            if not text:
                continue
            if e["speaker"].startswith("Maya"):
                mentor.history.append({"role": "assistant", "content": text})
                student.hear(text)
            else:
                student.history.append({"role": "assistant", "content": text})
                mentor.hear(text)
            transcript.append(e)
        # Make sure the mentor speaks next regardless of who spoke last.
        if entries and entries[-1]["speaker"].startswith("Maya"):
            mentor.hear("(The session was interrupted and has just been restored. Continue from where you left off.)")
        print(f"Resumed run {stamp}: {len(entries)} turns restored, lesson {memory.current_lesson}.")

    def record(speaker: str, text: str) -> None:
        transcript.append({"speaker": speaker, "lesson": memory.current_lesson, "text": text})
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(transcript[-1], ensure_ascii=False) + "\n")
        print(f"\n----- {speaker} (lesson {memory.current_lesson}) -----\n{text}")

    # Kick off: the mentor opens the course.
    if not resume:
        mentor.hear("(The student has joined the chat. Begin the course.)")

    for _ in range(MAX_TURN_PAIRS - len(transcript) // 2):
        raw = mentor.speak(memory_block=memory.to_block())
        visible, update, parse_err = extract_memory_update(raw)
        visible = scrub_memory_blocks(visible)  # belt and braces: nothing leaks

        system_note = ""
        if update is not None:
            result = memory.apply_update(update)
            memory.save(memory_path)
            if result.startswith("error"):
                system_note = f"(SYSTEM: your memory update was refused — {result})"
        elif parse_err:
            system_note = f"(SYSTEM: {parse_err} — re-read the memory protocol and include the block next turn)"

        record("Maya (mentor)", visible)
        if COMPLETE_MARK in visible:
            break
        student.hear(visible.replace(COMPLETE_MARK, "").strip())

        # Scrub the student's output too: live runs showed models echoing the
        # protocol after glimpsing a malformed block.
        student_text = scrub_memory_blocks(student.speak())
        record("Denis (student)", student_text)
        heard = student_text if not system_note else f"{system_note}\n\n{student_text}"
        mentor.hear(heard)

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
