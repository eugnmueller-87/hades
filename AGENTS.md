# AGENTS.md — Hades Supplier Due Diligence Agent

## Identity

**Name:** Hades  
**Role:** Autonomous supplier due diligence agent — gatekeeper for vendor onboarding in the SpendLens procurement stack  
**Live URL:** `https://hades-production-b86a.up.railway.app`  
**Model:** Claude Sonnet 4.6  
**Framework:** LangGraph StateGraph (FastAPI wrapper)

---

## What This Agent Does

Hades receives a company name, procurement category, and country. It autonomously:

1. Reads existing Hermes market intelligence (pre-flight)
2. Runs 6 parallel research pipelines (sanctions, registry, news, LkSG/CSDDD, ESG, web)
3. Synthesises all findings into a weighted risk score across 6 dimensions
4. Generates a structured due diligence report with a clear recommendation
5. Registers the supplier in Hermes for ongoing monitoring
6. Persists the full audit record to Redis

**Output:** Structured JSON report with risk score (1–10), recommendation (Approve / Conditional Approval / Block), dimension breakdown, compliance signals, and required next steps.

---

## Trigger

```http
POST /investigate
Content-Type: application/json

{
  "company": "Robert Bosch GmbH",
  "category": "Electronics",
  "country": "DE",
  "mode": "full"
}
```

`mode` is optional. Values: `"full"` (default) or `"recheck"`.

The agent runs fully autonomously from this trigger — no further input required.

---

## Tools & APIs

| Tool | Purpose | Always runs? |
|---|---|---|
| Hermes Redis (`hermes:supplier:<slug>`) | Pre-flight: read existing market signals | Yes |
| Serper.dev | Web research (4 queries), LkSG signals, ESG signals, registry fallback | Yes (reduced if Hermes hit) |
| newsapi.ai (Event Registry) | News sentiment — last 90 days, EN + DE | Skipped if Hermes has >10 signals |
| OFAC SDN XML | US Treasury sanctions list — parsed from free XML, 24h cache | Always |
| UN SC Consolidated List XML | UN Security Council sanctions — parsed from free XML, 24h cache | Always |
| Upstash Redis | Read Hermes signals pre-flight; write audit record + watchlist entry post-report | Always |

**Minimum APIs for a valid report:** Serper.dev + Anthropic. All others degrade gracefully.

---

## LangGraph Pipeline

```
hermes_preflight
      │
  ┌───┴──────────────────────────────────────────┐
  │ parallel (Send API fan-out)                  │
  │  web_research   sanctions_check              │
  │  news_sentiment registry_lookup              │
  │  lksg_signals   esg_signals                  │
  └──────────────────┬───────────────────────────┘
                     │
                synthesis         ← Claude: score 6 dimensions
                     │
            report_generator      ← Claude: structured JSON report
                     │
            hermes_register       ← write watchlist entry
                     │
             audit_writer         ← persist audit record (Redis list, newest first, max 50)
                     │
                    END
```

**State object:** `DDState` TypedDict defined in `agent/state.py`. Each node reads from and writes to state — no side-channel communication between nodes.

---

## Risk Scoring

Claude scores each dimension independently based on research outputs:

| Dimension | Weight | Score drives recommendation toward Block when... |
|---|---|---|
| Sanctions & Watchlists | 25% | Score ≥ 9 (priority OFAC/UN match) |
| LkSG / CSDDD Compliance | 20% | Score ≥ 7 (BAFA enforcement or NGO red flag) |
| Company Registry | 15% | Score ≥ 7 (dissolved, insolvent, jurisdiction flag) |
| News Sentiment | 15% | Score ≥ 7 (high-severity negative coverage) |
| ESG & Labour | 15% | Score ≥ 7 (ILO violation, forced/child labour finding) |
| Hermes Intelligence | 10% | Score ≥ 7 (multiple HIGH urgency ongoing signals) |

**Hard rules (always enforced by Claude):**
- Confirmed sanctions hit with priority match → `recommendation = Block`, sanctions score ≥ 9
- LkSG `red_flag` signal → compliance score ≥ 7
- Dissolved or insolvent company → registry score ≥ 7

**Thresholds:**
- Low: 1.0–3.9 → Approve
- Medium: 4.0–6.4 → Conditional Approval
- High: 6.5–7.9 → Conditional Approval or Block
- Critical: 8.0–10.0 → Block

---

## Constraints & Guardrails

- **No hallucination of sources.** Claude must cite only data returned by the research nodes. If a source returns no data, Claude must say so — not invent findings.
- **Structured output only.** Both synthesis and report_generator use Claude tool_use to produce JSON. Free-text narrative is only allowed inside designated string fields (`executive_summary`, `rationale`).
- **Audit failure is non-fatal.** If `audit_writer` fails, the DD response is still returned. The exception is swallowed silently — audit failure must never break the user-facing response.
- **Hermes registration is idempotent.** If the supplier is already on the Hermes watchlist, `register_vendor()` returns `False` and does nothing. No duplicate entries.
- **No PII or credentials in state.** `DDState` contains company data and research outputs only.

---

## API Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/investigate` | Run full DD pipeline | X-API-Key |
| GET | `/audit/{company}` | Full investigation history (newest first, max 50) | X-API-Key |
| GET | `/audit/{company}/latest` | Most recent audit record only. Returns 404 if none. | X-API-Key |
| GET | `/audit/export/csv` | Portfolio CSV — all investigated suppliers | X-API-Key |
| GET | `/audit/{company}/export/csv` | Single supplier audit trail as CSV | X-API-Key |
| GET | `/health` | `{"status": "ok", "agent": "hades", "version": "0.1.0"}` | Public |

---

## Environment Variables Required

```
ANTHROPIC_API_KEY          Claude Sonnet 4.6
SERPER_API_KEY             Web research + LkSG/ESG queries
NEWSAPI_KEY                newsapi.ai (Event Registry) — UUID format
UPSTASH_REDIS_REST_URL     Shared with Hermes and SpendLens
UPSTASH_REDIS_REST_TOKEN   Shared with Hermes and SpendLens
```

Hades validates all 5 at startup and refuses to start if any are missing.

**Optional:**

```
HADES_API_KEY              API-key auth for all endpoints except /health.
                           Comma-separated for multiple consumers (Icarus,
                           SpendLens). If unset, the API runs OPEN and logs a
                           warning at startup.
INVESTIGATE_RATE_LIMIT     Max /investigate requests per window (default 10).
INVESTIGATE_RATE_WINDOW    Rate-limit window in seconds (default 3600).
LOG_LEVEL                  Logging level (default INFO).
```

## Authentication

Every endpoint except `/health` requires a valid key in the `X-API-Key`
header when `HADES_API_KEY` is set. Keys are compared in constant time.
Callers without a valid key receive `401`. `/health` is always public so the
Railway healthcheck keeps working. If `HADES_API_KEY` is unset, auth is
disabled (open API) and a warning is logged — provision the key before
exposing the service.

```http
POST /investigate
X-API-Key: <your-key>
Content-Type: application/json
```

---

## Skills (Icarus Integration)

Hades exposes 4 tools to Icarus (Telegram bot):

| Skill | Trigger phrase | What it does |
|---|---|---|
| `hades_supplier_lookup` | "Is Bechtle a supplier?" | Calls SpendLens spend data + Hades audit in parallel — one combined answer |
| `hades_report` | "Pull the DD report for Bosch" | Returns latest audit record with full dimension breakdown |
| `hades_audit` | "Show me the audit trail for SAP" | Returns all investigations newest first |
| `hades_export` | "Export supplier report" | Downloads CSV, sends as Telegram document attachment |

Skills source: `Personal-Assistent/bot/skills/hades.py`

---

## Error Handling Policy

| Failure | Behaviour |
|---|---|
| External API down (Serper, NewsAPI) | Node returns empty result; synthesis scores that dimension as unknown (score 5, neutral) |
| Sanctions XML fetch fails | Node returns `{"error": "unavailable"}`; synthesis flags this explicitly in the report |
| Hermes Redis unreachable (pre-flight) | `skip_news = False`; all nodes run full; no crash |
| `audit_writer` fails | Exception swallowed; DD report still returned |
| Claude returns malformed JSON | `parse_json_response()` in `_utils.py` retries with a correction prompt once |
| HTTP 5xx from Hades (SpendLens proxy) | `raise_for_status()` propagates as `HTTPException(5xx)` to SpendLens caller |
