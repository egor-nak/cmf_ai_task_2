# Mentor That Knows You Learned

Multi-agent simulation for the AI School assignment: a **mentor** agent teaches a
10-lesson prompt-engineering course to a **student** agent that sometimes fakes
having done the practice. The mentor must detect bluffing and refuse to advance
until it has real evidence of application — using conversation alone.

## Repo layout

```
prompts/mentor_system.md    Mentor persona + verification doctrine + bluff protocol
prompts/student_system.md   Student persona + unreliability rule
course/curriculum.json      10 lessons, each with skill, practice, verification questions, red flags
src/agents.py               Anthropic API agent wrapper (each agent keeps its own history)
src/memory.py               Mentor memory tool — enforces "no advance without verified" in code
src/orchestrator.py         Turn-by-turn loop, transcript capture (md + jsonl)
src/run_course.py           Entry point
transcripts/                Captured runs
SUBMISSION.md               The single submission document (all 5 required sections)
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
python -m src.run_course
```

The full dialogue streams to stdout and is saved to `transcripts/run-<stamp>.md`
(plus a `.jsonl` and the mentor's final memory state).

## Design notes (short version — full rationale in SUBMISSION.md)

- **Two views of one dialogue.** Each agent holds its own message history where
  the other agent is the "user". No shared context leakage between personas.
- **Memory as a tool, verification as code.** The mentor records per-lesson
  verdicts (`verified` / `shaky` / `caught-bluffing`) via `update_memory`. The
  tool *refuses* to advance the course pointer past an unverified lesson, so the
  advancement rule is enforced mechanically, not just in prose.
- **Verification questions written before lesson content** (per the assignment
  tip): each curriculum entry carries an application question, a live transfer
  test, and explicit red flags the mentor watches for.
