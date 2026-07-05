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

## Run it — on free/cheap models

The runner speaks the OpenAI-compatible API, so it works with any of:

| Provider | Cost | Setup |
|---|---|---|
| **OpenRouter** (default) | free tier | key from https://openrouter.ai; pick a current `:free` model at https://openrouter.ai/collections/free-models |
| **Groq** | free tier, fast | key from https://console.groq.com |
| **Ollama** | 100% free, local | `ollama pull qwen3:8b`, no key needed |

```bash
# no pip install needed — zero dependencies, Python 3.10+ only
cp .env.example .env        # pick provider + model, add key (see options inside)
export $(grep -v '^#' .env | xargs)
python3 -m src.run_course
```

The full dialogue streams to stdout and is saved to `transcripts/run-<stamp>.md`
(plus a `.jsonl` and the mentor's final memory state).

**Free-tier notes:** OpenRouter free models are rate-limited (~20 req/min,
200 req/day) — `COURSE_SLEEP` throttles calls to fit. A full course run is
roughly 100–200 API calls, so it fits in one day's free quota, barely; Ollama
has no limits at all. Free model IDs change without warning — verify yours
exists before a long run.

## Design notes (short version — full rationale in SUBMISSION.md)

- **Two views of one dialogue.** Each agent holds its own message history where
  the other agent is the "user". No shared context leakage between personas.
- **Memory as a text protocol, verification as code.** The mentor ends every
  message with a `<memory>{...}</memory>` JSON block recording per-lesson
  verdicts (`verified` / `shaky` / `caught-bluffing`). The orchestrator strips
  it before the student sees anything and *refuses* to advance the course
  pointer past an unverified lesson — the rule is enforced mechanically, not
  just in prose. A text block (rather than native tool calling) was chosen so
  the same code runs on free models with no/flaky function-calling support.
- **Verification questions written before lesson content** (per the assignment
  tip): each curriculum entry carries an application question, a live transfer
  test, and explicit red flags the mentor watches for.
