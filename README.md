# Mentor That Knows You Learned

Multi-agent simulation for the AI School assignment: a **mentor** agent teaches a
10-lesson prompt-engineering course to a **student** agent that sometimes fakes
having done the practice. The mentor must detect bluffing and refuse to advance
until it has real evidence of application — using conversation alone.

**v2 — conversation-first redesign.** Both agents now text like humans (mentor
≤ ~50 words, student 5–25), the course opens with onboarding instead of a
lecture (enforced by a phase machine, not just the prompt), lessons are taught
through the student's own real task, and homework triggers a simulated
next-day session break. See `SUBMISSION.md` §5 for the full rationale.

**Final submitted run:** `transcripts/final_run.md` — 94 turn pairs, all ten
lessons verified, run live on **deepseek-v4-flash** via an OpenAI-compatible
API. (`transcripts/design_walkthrough.md` is the authored reference dialogue
the prompts were designed toward.)

## Repo layout

```
prompts/mentor_system.md    Mentor persona + verification doctrine + bluff protocol
prompts/student_system.md   Student persona + unreliability rule
course/curriculum.json      10 lessons, each with skill, practice, verification questions, red flags
src/agents.py               OpenAI-compatible agent wrapper (each agent keeps its own history)
src/memory.py               Mentor memory tool — enforces "no advance without verified" in code
src/orchestrator.py         Turn-by-turn loop, transcript capture (md + jsonl)
src/run_course.py           Entry point
transcripts/final_run.md    The submitted live run (deepseek-v4-flash)
transcripts/                Other captured runs (gitignored)
SUBMISSION.md               The single submission document (all 5 required sections)
```

## Run it — on free/cheap models

The runner speaks the OpenAI-compatible API, so it works with any of:

| Provider | Cost | Setup |
|---|---|---|
| **Qwen / Alibaba Model Studio** | trial token quota, then cents | key from https://modelstudio.console.alibabacloud.com; model `qwen-plus` (runner auto-sends `enable_thinking=false`) |
| **Groq** | free tier, fast | key from https://console.groq.com; `llama-3.3-70b-versatile` (~1,000 req/day) |
| **OpenRouter** | free tier (~50 req/day) | key from https://openrouter.ai; pick a current `:free` model at https://openrouter.ai/collections/free-models |
| **Ollama** | 100% free, local | `ollama pull qwen3:8b`, no key needed |

```bash
# no pip install needed — zero dependencies, Python 3.10+ only
cp .env.example .env        # pick provider + model, add your real key inside
python3 -m src.run_course   # .env is loaded automatically — no export/source step
```

The full dialogue streams to stdout and is saved to `transcripts/run-<stamp>.md`
(plus a `.jsonl` and the mentor's final memory state).

**Free-tier notes:** OpenRouter free models are rate-limited (~20 req/min;
~50 free-model requests/day, or ~1,000/day after a one-time $10 credit
purchase) — `COURSE_SLEEP` throttles calls to fit the per-minute cap. The
short-turn design needs roughly 230–280 API calls per full run, so either buy
the $10 unlock, use Groq, run locally on Ollama (no limits), or split the run
across days with `--resume`. Free model IDs change without warning — verify
yours exists before a long run.

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
