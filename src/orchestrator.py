"""Orchestrates the mentor-student conversation across the full course.

Loop shape:
    mentor speaks -> memory block parsed & applied -> student hears visible text
    -> student speaks -> mentor hears -> repeat

The mentor drives: it emits a <memory>{...}</memory> block each turn (see
src/memory.py). The orchestrator enforces, in code, the things prompts alone
can't guarantee on cheap models:

- ADVANCEMENT: an invalid advance (lesson N not verified) is refused and the
  error is fed back to the mentor.
- PHASE: during onboarding the mentor gets an onboarding brief (what profile
  facts are still missing) instead of lesson content — so the course cannot
  open with a lecture.
- BREVITY: if the mentor's visible message exceeds the word cap, it gets a
  system nudge on its next turn (real users skim or quit).
- SESSION CADENCE: when the mentor sets "end_session" after assigning
  practice, the orchestrator inserts a next-day marker for both agents,
  simulating the async rhythm of a real coaching app.

The loop ends when the mentor prints [COURSE_COMPLETE] after the final
assessment, or when the turn budget runs out (safety valve).
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
MAX_TURN_PAIRS = 180  # hard safety cap: short-turn design needs more, smaller turns
COMPLETE_MARK = "[COURSE_COMPLETE]"
MENTOR_WORD_CAP = 90  # nudge threshold (style cap is ~50; 90 = clearly rambling)
NEXT_DAY_MARK = "— next day —"

ONBOARDING_BRIEF = """
=== PHASE: ONBOARDING — DO NOT TEACH YET ===
You are getting to know a brand-new student. Missing profile facts: {missing}.
Ask ONE casual question per message; react like a human between questions.
When you know their job, their goal, and one real task from their week, set
{{"phase": "course"}} in your memory block and begin lesson 1 THROUGH that real
task — as help, not as a lesson announcement.
=== END PHASE ===""".rstrip()


def load_text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def build_mentor_system() -> str:
    # Lesson TITLES only — the current lesson's full entry is injected each
    # turn by mentor_context(). Embedding the whole curriculum here would cost
    # ~2.5K tokens on every call (free tiers cap tokens/day, not just requests).
    prompt = load_text("prompts/mentor_system.md")
    cur = json.loads(load_text("course/curriculum.json"))
    titles = "\n".join(f"{l['id']}. {l['title']}" for l in cur["lessons"])
    return (
        f"{prompt}\n{MEMORY_PROTOCOL}\n"
        f"## Course: {cur['course_title']} — lessons in order\n{titles}\n\n"
        f"(The current lesson's full entry — skill, practice, verification, "
        f"red flags — is provided in context every turn.)\n\n"
        f"When the final assessment after lesson 10 is delivered, end your last "
        f"message (before the memory block) with the exact marker {COMPLETE_MARK}."
    )


# Fragments that mean an agent leaked reasoning or protocol instead of
# speaking in character. Deliberately specific: normal dialogue never
# contains these strings.
LEAK_MARKERS = (
    "advance_to_lesson", "lesson_status", "<memory", "memory block",
    "we need to respond", "we need to produce", "we need to output",
    "the user message", "as maya", "as denis", "the assistant",
    "system prompt", "our previous", "role-play",
)


def looks_leaky(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in LEAK_MARKERS)


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
    # Per-agent token budgets: the student texts in fragments, the mentor in
    # 1-3 sentences. Small budgets double as a brevity backstop and cost cap.
    mentor = Agent("Maya (mentor)", build_mentor_system(), max_tokens=700)
    student = Agent("Denis (student)", load_text("prompts/student_system.md"), max_tokens=350)

    lessons = {l["id"]: l for l in json.loads(load_text("course/curriculum.json"))["lessons"]}

    def mentor_context() -> str:
        """Memory block + phase-appropriate brief, re-injected every turn so
        weak free models can't drift off-curriculum (or into lecturing)."""
        block = memory.to_block()
        if memory.phase == "onboarding":
            missing = [k for k in ("job", "goal", "real_task") if k not in memory.user_profile]
            block += "\n" + ONBOARDING_BRIEF.format(
                missing=", ".join(missing) if missing else "none — switch phase to 'course' now"
            )
            return block
        lesson = lessons.get(memory.current_lesson)
        if lesson:
            block += (
                "\n=== CURRENT LESSON (teach exactly this, no other) ===\n"
                + json.dumps(lesson, ensure_ascii=False, indent=1)
                + "\n=== END CURRENT LESSON ==="
            )
        return block

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
            if e["speaker"] == "⏱":  # next-day marker, not a dialogue turn
                transcript.append(e)
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

    # Kick off: a new student appears; the mentor says hi (no teaching yet —
    # the onboarding brief in mentor_context() enforces that).
    if not resume:
        mentor.hear("(A new student has just joined the chat. Say hi.)")

    pending_day_break = False  # set when the previous mentor turn ended a session

    for _ in range(MAX_TURN_PAIRS - len(transcript) // 2):
        # --- Mentor turn, validated BEFORE the student sees anything. ---
        # A bad turn (leaked reasoning/protocol, missing memory block, empty
        # text) is erased from the mentor's own history and regenerated with a
        # corrective note — the one-turn-too-late feedback of v1 let a single
        # malformed message contaminate the whole dialogue.
        visible, update, parse_err = "", None, None
        for _attempt in range(3):
            raw = mentor.speak(memory_block=mentor_context())
            visible, update, parse_err = extract_memory_update(raw)
            visible = scrub_memory_blocks(visible)  # belt and braces: nothing leaks
            if visible and update is not None and not looks_leaky(visible):
                break
            mentor.history.pop()  # erase the bad attempt
            mentor.hear(
                "(SYSTEM: your last output was invalid — it leaked internal "
                "reasoning/protocol text, or lacked the <memory> block. Send it "
                "again properly: a short in-character chat message to the student, "
                "then the <memory>{...}</memory> block on its own line. Nothing else.)"
            )

        system_note = ""
        end_session = False
        if update is not None:
            end_session = bool(update.get("end_session"))
            result = memory.apply_update(update)
            memory.save(memory_path)
            if result.startswith("error"):
                system_note = f"(SYSTEM: your memory update was refused — {result})"
        elif parse_err:
            system_note = f"(SYSTEM: {parse_err} — re-read the memory protocol and include the block next turn)"

        if not visible:  # all retries failed — keep the dialogue alive
            visible = "sorry, one sec — hit send too early."

        # Brevity guard: prompts ask for ~50 words; cheap models drift. Nudge.
        wc = len(visible.split())
        if wc > MENTOR_WORD_CAP:
            system_note += (
                f" (SYSTEM: your last message was {wc} words — the cap is ~50. "
                f"Real users skim or quit. One idea, one question, shorter.)"
            )

        record("Maya (mentor)", visible)
        if COMPLETE_MARK in visible:
            break
        student_hears = visible.replace(COMPLETE_MARK, "").strip()
        if pending_day_break:
            student_hears = "(It is now the next day.)\n\n" + student_hears
            pending_day_break = False
        student.hear(student_hears)

        # --- Student turn, validated the same way: scrub, detect leaks, retry.
        student_text = ""
        for _attempt in range(3):
            student_text = scrub_memory_blocks(student.speak())
            if student_text and not looks_leaky(student_text):
                break
            student.history.pop()  # erase the bad attempt
            student.hear(
                "(SYSTEM: invalid output — you are Denis texting his coach. "
                "Reply again with ONLY Denis's next short casual message. "
                "No JSON, no protocol text, no analysis of the conversation.)"
            )
        record("Denis (student)", student_text)
        heard = student_text if not system_note.strip() else f"{system_note.strip()}\n\n{student_text}"
        if end_session:
            # Simulate the async coaching cadence: practice happens off-screen
            # overnight; both agents get a time marker.
            record("⏱", NEXT_DAY_MARK)
            heard += "\n\n(-- Session over. It is now the next day; the student is back. --)"
            pending_day_break = True
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
