# Pushing this repo to GitHub

Everything is already committed locally (7 commits, branch `main`, `.env` safely gitignored). You only need to connect and push.

## Option A — GitHub website + terminal (no extra tools)

1. **Create an empty repo on GitHub:** github.com → **+** → **New repository** → name it (e.g. `mentor-student-agents`) → **do NOT** add a README, .gitignore, or license (the repo must stay empty) → Create.

2. **Push** (in Terminal, inside this folder):

```bash
cd ~/Claude/Projects/AI_angents_task_cmf
git remote add origin https://github.com/YOUR_USERNAME/mentor-student-agents.git
git push -u origin main
```

3. When asked for a password, use a **Personal Access Token**, not your account password: github.com → Settings → Developer settings → Personal access tokens → **Generate new token (classic)** → tick `repo` scope → copy it and paste as the password.

## Option B — GitHub CLI (fastest)

```bash
brew install gh          # if not installed
gh auth login            # follow browser prompts
cd ~/Claude/Projects/AI_angents_task_cmf
gh repo create mentor-student-agents --public --source=. --push
```

## Verify

Open `https://github.com/YOUR_USERNAME/mentor-student-agents` — you should see:
README.md, SUBMISSION.md, `prompts/`, `course/`, `src/`, `transcripts/`, and 7 commits.

## What's included / excluded

- **Included:** all assignment deliverables — SUBMISSION.md (the submission document), prompts, curriculum, orchestrator code, full transcript, README.
- **Excluded by .gitignore (correctly):** `.env` (your API key — never push this), `__pycache__/`, generated `transcripts/run-*` files. If you produce a live run you want to submit, add it explicitly: `git add -f transcripts/run-XXXX.md && git commit -m "add live run" && git push`.

## Submitting

Share the repo URL, or if your school wants a file: SUBMISSION.md is the single document with all five required sections.
