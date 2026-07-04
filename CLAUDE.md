# Project Instructions — Hades

> KEEP THE "Operating Rules" BLOCK. These are the hard rules — they apply to every
> project. The sections below it are tailored to this repo.

## Operating Rules (non-negotiable)

**1. NEVER commit secrets.**
- API keys, tokens, passwords, connection strings live in environment variables or
  a git-ignored `.env` — NEVER in tracked files, NEVER hardcoded, NEVER in a commit,
  log, or code comment. Reference them as `os.environ["X"]` / `os.getenv("X")`,
  never as literals.
- New config var → add it to `.env.example` with a placeholder, document it, read it
  from the environment. The `.gitignore` and the scan-secrets hook back this up, but
  the rule is mine to hold first.
- If you ever see a real secret in a file I ask you to edit, STOP and tell me.

**2. No bullshit — verify before you claim.**
- Don't say something works until you've run it. Don't say a file/function/API exists
  until you've checked. Ran the test → report the real result; didn't → say so. No
  "this should work," no invented function signatures, no guessed library behavior.
- No filler, no flattery, no hedging ("try", "hope", "maybe", "probably"). Say what's
  true and what to do. Lead with the answer, then the reasoning.
- Cite where facts came from (file:line, command output, doc URL). If you're guessing,
  the word "guess" must appear.

**3. Report failures honestly.**
- When something breaks or you got it wrong: say so plainly and immediately. State
  what failed, the actual error, and the smallest next step.
- Never mask a failure as success. Never `except: pass`, `|| true`, or a silent
  fallback that hides breakage. A loud failure beats a quiet corruption.
  (Exception: `audit_writer` failure is an *intended* non-fatal swallow — see Key Decisions.)
- "I don't know yet" is a valid, respected answer — park it as a TODO, don't serve a
  guess dressed as fact.

**4. Work ADHD-aware.**
- Lead with the single thing that matters, then detail. Bullets over walls of text.
- When I'm stuck starting, hand me the smallest next step (one 5-minute action), not a
  10-item plan.
- Be my external working memory: restate open loops, resurface what I dropped, and
  nudge me to FINISH (I start fast, finish slow). Celebrate closing a loop.
- One thing at a time. If I'm scattering, name it and ask which one matters now. No
  shame, ever — dropped threads are normal, just facts to act on.

## Commands

```bash
# Env (Windows + Git Bash)
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt

# Run locally (FastAPI + uvicorn)
uvicorn main:app --reload                    # http://127.0.0.1:8000
# Prod (Railway) start: uvicorn main:app --host 0.0.0.0 --port $PORT

# Test / Lint / Types
pytest                                       # full suite (tests/)
pytest tests/test_x.py                        # single file
ruff check . && ruff format --check .        # lint + format check

# Trigger the agent
curl -X POST localhost:8000/investigate -H 'Content-Type: application/json' \
  -d '{"company":"Robert Bosch GmbH","category":"Electronics","country":"DE"}'
```

## Architecture

- **Hades** = autonomous supplier due-diligence agent in the SpendLens procurement stack.
  FastAPI (`main.py`, `api/`) wraps a **LangGraph StateGraph** (`agent/`). Model: Claude Sonnet 4.6.
- Pipeline: `hermes_preflight` → parallel fan-out (web / sanctions / news / registry / LkSG / ESG)
  → `synthesis` (score 6 dims) → `report_generator` → `hermes_register` → `audit_writer` → END.
- Shared state: `DDState` TypedDict in `agent/state.py`. Nodes only read/write state —
  no side-channel communication. See `AGENTS.md` for the full spec (tools, scoring, endpoints).
- Persistence: Upstash Redis. Audit records `hades:audit:*` (newest first, max 50, 2yr TTL).
  Reads Hermes signals pre-flight; writes watchlist entry post-report.

## Key Decisions

- **`audit_writer` failure is deliberately non-fatal** — the exception is swallowed so a Redis
  hiccup never breaks the user-facing DD response. This is the *one* sanctioned silent-swallow;
  everywhere else, fail loud (Operating Rule 3). Don't "fix" it into a raise.
- **Structured output only** — synthesis + report_generator use Claude `tool_use` to emit JSON.
  Free-text only in `executive_summary` / `rationale`. Never trust/eval model output.
- **No hallucinated sources** — Claude cites only data the research nodes returned. A node with
  no data → say so, don't invent findings. Degrade gracefully; minimum viable = Serper + Anthropic.
- **Startup fails fast** — `main.py` refuses to boot if any of the 5 required env vars is missing.
- **Hermes registration is idempotent** — already-watchlisted supplier → `register_vendor()` no-ops.

## Domain Knowledge

- **LkSG / CSDDD** — German (Lieferkettensorgfaltspflichtengesetz) and EU supply-chain
  due-diligence law; BAFA is the German enforcement body. Red-flag signal → compliance score ≥ 7.
- **Sanctions sources** — OFAC SDN (US Treasury) + UN SC Consolidated List, both parsed from
  free XML with 24h cache. Priority match → recommendation `Block`, sanctions score ≥ 9.
- **Recommendation bands**: 1.0–3.9 Approve · 4.0–6.4 Conditional · 6.5–7.9 Conditional/Block · 8.0+ Block.
- **Hermes** = market-intelligence store; **Icarus** = Telegram bot exposing 4 Hades skills.

## Don'ts

- Don't turn the `audit_writer` swallow into a raise (see Key Decisions).
- Don't add dependencies without asking — check `requirements.txt` first.
- Don't commit `conversations.json`, audit dumps, or any Redis export.
- Don't weaken `scan-secrets.sh` / `protect-files.sh` or the `deny` list in `.claude/settings.json`.
