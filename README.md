# Hades — Supplier Due Diligence Agent

**Hades** is the gatekeeper of the SpendLens procurement stack. It autonomously researches any supplier and generates a structured due diligence report — covering sanctions, company registry, news sentiment, LkSG/CSDDD compliance, ESG signals, and live Hermes market intelligence — in under 2 minutes. No manual research. No spreadsheets.

> **SpendLens procurement stack:** Icarus (personal AI OS) · SpendLens (spend analytics) · **Hades** (supplier vetting) · Hermes (market intelligence)

**Live:** `https://hades-production-b86a.up.railway.app`

---

## Screenshot

![Hades — Bosch investigation, High risk, score 5.0, investigation pipeline complete](screenshots/Screenshot%202026-05-16%20205825.png)

---

## Full Stack Architecture

This is the complete picture — four AI systems interacting to handle the entire procurement intelligence lifecycle.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ICARUS (Personal AI OS)                        │
│                     Telegram bot · Claude Sonnet 4.6 · icarusai.de         │
│                                                                             │
│  User: "Is Bechtle a supplier?"          User: "Export supplier CSV"        │
│         │                                         │                         │
│         ▼                                         ▼                         │
│  hades_supplier_lookup ──────────────── hades_export                        │
│    (runs in parallel)                    (calls Hades API,                  │
│         │          │                     sends CSV as                       │
│         │          │                     Telegram document)                 │
│         ▼          ▼                                                        │
└─── SpendLens ── Hades ───────────────────────────────────────────────────┘
         │             │
         │    checks active spend             checks audit Redis
         │    in vendor DB                    for prior DD records
         │             │
         │     ┌───────┴──────────────────────────────────────────────┐
         │     │                 HADES  (this agent)                  │
         │     │                                                      │
         │     │  hermes_preflight ── reads Hermes Redis pre-flight   │
         │     │       │                                              │
         │     │  ┌────┴─────────────────────────────────────────┐   │
         │     │  │              parallel fan-out                │   │
         │     │  │  web_research    news_sentiment              │   │
         │     │  │  sanctions_check registry_lookup             │   │
         │     │  │  lksg_signals    esg_signals                 │   │
         │     │  └──────────────────┬───────────────────────────┘   │
         │     │                     │                               │
         │     │               synthesis  ← Claude Sonnet 4.6        │
         │     │                     │                               │
         │     │           report_generator ← Claude Sonnet 4.6      │
         │     │                     │                               │
         │     │           hermes_register ── writes to watchlist    │
         │     │                     │                               │
         │     │            audit_writer ── persists to Redis        │
         │     └───────────────────────────────────────────────────┘
         │                           │
         │                           ▼
         │          ┌────────────────────────────────┐
         │          │     HERMES (market intel)      │
         │          │  Upstash Redis · Upstash Vector │
         │          │  ~590 suppliers · 17 categories │
         │          │  RSS · EDGAR · Tavily · Jobs    │
         │          │  Claude Haiku (signal class.)   │
         │          └────────────────────────────────┘
         │                           │
         └── vendor DB updated ──────┘
             (hades_risk_score,
              hades_recommendation, ...)
```

### How the four systems communicate

| From | To | What | When |
|---|---|---|---|
| SpendLens UI | Hades | `POST /investigate` | New vendor created or periodic recheck |
| Icarus | SpendLens | `GET /api/suppliers/lookup/{name}` | User asks "is X a supplier?" |
| Icarus | Hades | `GET /audit/{company}/latest` | User asks "is X onboarded?" or "pull DD report" |
| Icarus | Hades | `GET /audit/export/csv` | User says "export supplier report" |
| Hades | Hermes Redis | `lpush hades:audit:<slug>` | After every investigation (audit trail) |
| Hades | Hermes Redis | `set hermes:watchlist:<slug>` | Registers supplier for ongoing monitoring |
| Hermes | Hermes Redis | `get hermes:supplier:<slug>` | Hades pre-flight reads live market intel |

---

## What Hades Does

Send `POST /investigate` with a company name, category, and country. Hades runs 6 parallel research pipelines and returns a full structured risk report with:

- **Overall risk score** (1–10, weighted across 6 dimensions)
- **Recommendation**: `Approve` / `Conditional Approval` / `Block`
- **Executive summary** in plain language
- **Company registry details** — HRB number, Amtsgericht, legal status
- **Sanctions status** — OFAC SDN + UN SC Consolidated List
- **LkSG/CSDDD compliance signal** — `no_findings` / `needs_monitoring` / `red_flag`
- **ESG & labour risk** — EcoVadis, ILO, Transparency Intl, Violation Tracker
- **Required next steps** surfaced to the procurement manager
- **Hermes integration** — reads prior intelligence pre-flight, registers new suppliers post-report for ongoing monitoring
- **Persistent audit trail** — every investigation saved to Redis, queryable via API

### Risk Score Weights

| Dimension | Weight | Data Source |
|---|---|---|
| Sanctions & Watchlists | 25% | OFAC SDN XML + UN SC Consolidated List (free, no API key) |
| LkSG / CSDDD Compliance | 20% | BAFA, OECD NCP, ECCHR/NGO signals via Serper |
| Company Registry | 15% | NorthData + Unternehmensregister via Serper |
| News Sentiment | 15% | newsapi.ai (Event Registry) — last 90 days |
| ESG & Labour | 15% | EcoVadis, ILO, Transparency Intl, Violation Tracker |
| Hermes Intelligence | 10% | Upstash Redis — live SpendLens market signals |

**Risk thresholds:** Low = 1.0–3.9 · Medium = 4.0–6.4 · High = 6.5–7.9 · Critical = 8.0–10.0

**Hard rules always enforced by Claude:**
- Sanctioned entity with priority hit → sanctions score ≥ 9, recommendation = Block
- LkSG red flag → compliance score ≥ 7
- Dissolved / insolvent company → registry score ≥ 7

---

## Internal Pipeline

```
POST /investigate
       │
  hermes_preflight          ← reads Hermes Redis; skips NewsAPI if signal_count > 10
       │
  ┌────┴──────────────────────────────────────────────┐
  │            parallel LangGraph fan-out             │
  │  web_research   news_sentiment   sanctions_check  │
  │  registry_lookup   lksg_signals   esg_signals     │
  └────────────────────────┬──────────────────────────┘
                           │
                       synthesis              ← Claude Sonnet 4.6: scores 6 dimensions
                           │
                   report_generator          ← Claude Sonnet 4.6: full structured JSON
                           │
                   hermes_register           ← writes supplier to Hermes watchlist
                           │
                    audit_writer             ← persists full audit record to Redis
                           │
                          END
```

**Stack:** FastAPI · LangGraph StateGraph · Claude Sonnet 4.6 · Upstash Redis · Serper · newsapi.ai · OFAC SDN XML · UN SC XML

---

## API

### `POST /investigate`

```json
{
  "company": "Robert Bosch GmbH",
  "category": "Electronics",
  "country": "DE",
  "mode": "full"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company` | string | yes | Legal company name |
| `category` | string | yes | Procurement category |
| `country` | string | no | ISO-2 country code (default: `"DE"`) |
| `mode` | string | no | `"full"` (default) or `"recheck"` |

**Response** (key fields):

```json
{
  "company": "Robert Bosch GmbH",
  "hermes_registered": true,
  "report": {
    "overall_risk_score": 4.7,
    "risk_level": "Medium",
    "recommendation": "Conditional Approval",
    "executive_summary": "...",
    "dimension_scores": {
      "sanctions": 4,
      "registry": 2,
      "news_sentiment": 2,
      "lksg_csddd": 7,
      "esg_labour": 6,
      "hermes_intelligence": 3
    },
    "lksg_csddd_assessment": { "compliance_signal": "red_flag", "flagged_count": 12 },
    "required_next_steps": ["Request LkSG self-declaration", "..."]
  }
}
```

### `GET /audit/{company}`

Returns the full investigation history for a supplier, newest first (up to 50 records).

```json
{
  "company": "Bechtle AG",
  "investigation_count": 3,
  "history": [
    {
      "investigated_at": "2026-05-18T14:22:00",
      "mode": "full",
      "overall_risk_score": 3.2,
      "risk_level": "Low",
      "recommendation": "Approve",
      "dimension_scores": { "sanctions": 2, "registry": 1, ... },
      "lksg_signal": "no_findings",
      "hermes_tracked": true,
      "required_next_steps": []
    }
  ]
}
```

### `GET /audit/{company}/latest`

Returns only the most recent audit record. Returns `404` if no records exist.

### `GET /audit/export/csv`

Downloads the full audit history for **all** investigated suppliers as a CSV file.

**Columns:** `company · investigated_at · mode · category · country · overall_risk_score · risk_level · recommendation · sanctions_hit · sanctions_manual_review · lksg_signal · lksg_flagged_count · esg_rating · company_status · hrb · dim_sanctions · dim_registry · dim_news_sentiment · dim_lksg_csddd · dim_esg_labour · dim_hermes_intelligence · hermes_tracked · hermes_registered · required_next_steps`

### `GET /audit/{company}/export/csv`

Downloads the audit trail for a **single supplier** as a CSV file.

### `GET /health`

```json
{ "status": "ok", "agent": "hades", "version": "0.1.0" }
```

---

## Audit Trail

Every investigation is persisted to Upstash Redis as a structured record:

```
Redis key: hades:audit:<slug>
Type:      List (newest first, capped at 50 per supplier)
```

This means:
- Audit data **survives Railway redeployments** (Redis, not filesystem)
- Risk score changes are trackable over time
- Icarus can query history directly: "has Bechtle's risk score changed?"
- CSV export available for portfolio-level review

---

## Icarus Integration (Telegram)

Icarus exposes three Hades-related tools to the user via Telegram:

| Tool | Example prompts | What it does |
|---|---|---|
| `hades_supplier_lookup` | "Is Bechtle a supplier?" · "Have we checked Siemens?" | Calls SpendLens spend data AND Hades audit in parallel — one combined answer |
| `hades_report` | "Pull the DD report for Bosch" · "What's the risk score for SAP?" | Returns full latest audit record with dimension breakdown |
| `hades_audit` | "Show me the audit trail for Bechtle" · "How many times have we checked Bosch?" | Returns all investigations newest first |
| `hades_export` | "Export supplier report" · "Send me a CSV for Bechtle" | Downloads CSV from Hades API, sends as Telegram document |

---

## When SpendLens calls Hades

| Trigger | Mode | Effect |
|---|---|---|
| New vendor created, pending approval | `"mode": "full"` | Full 6-node research; supplier added to Hermes watchlist |
| Existing vendor periodic recheck | `"mode": "recheck"` | Same pipeline; Hermes data pre-loaded if tracked |

### What Hades writes back

SpendLens gates the onboarding decision on `report.recommendation`:

| Value | Meaning |
|---|---|
| `Approve` | Low risk — auto-approve or standard review |
| `Conditional Approval` | Medium/elevated risk — procurement manager review required |
| `Block` | Critical risk or sanctions hit — vendor blocked |

---

## Demo Scenarios

Run `demo/run_demo.py` with the server live (`uvicorn main:app --reload`):

```bash
python demo/run_demo.py
```

| Scenario | Company | Score | Risk | Recommendation |
|---|---|---|---|---|
| Clean DACH supplier (new to Hermes) | Schindler Group (CH) | 5.0 | Medium | Conditional Approval |
| LkSG/ESG-exposed supplier | H&M Group (SE) | 6.0 | High | Conditional Approval |
| Geopolitical + sanctions adjacency | Huawei Technologies (CN) | 7.0 | High | Block |
| Re-check — Hermes delta visible | Schindler Group (CH) | 4.0 | Medium | Conditional Approval |

Scenario 4 demonstrates the Hermes feedback loop: Schindler was added to the watchlist in Scenario 1; on re-check, `tracked_by_hermes: true` and Hermes pre-flight data is visible in the score.

---

## Setup

### Requirements

- Python 3.11+
- API keys: Anthropic, Serper.dev, newsapi.ai (Event Registry), Upstash Redis

### Local run

```bash
git clone https://github.com/eugnmueller-87/hades.git
cd hades
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # fill in your keys
uvicorn main:app --reload
```

Quick test:

```bash
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -d '{"company": "Siemens AG", "category": "Electronics", "country": "DE"}'
```

### Environment variables

```env
ANTHROPIC_API_KEY=sk-ant-...
SERPER_API_KEY=...
NEWSAPI_KEY=...                        # newsapi.ai UUID format
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...
```

Hades validates all 5 variables at startup and refuses to start if any are missing.

---

## LkSG / CSDDD Context

The **Lieferkettensorgfaltspflichtengesetz (LkSG)** — German Supply Chain Due Diligence Act — has been in force since January 2023 for companies with 1,000+ employees. It mandates risk-based due diligence across the full supply chain: human rights, environmental obligations, and grievance mechanisms.

The EU **CSDDD** (Corporate Sustainability Due Diligence Directive) extends equivalent requirements across all EU member states from 2026.

Hades checks three authoritative sources for LkSG/CSDDD signals:

- **BAFA** (Bundesamt für Wirtschaft und Ausfuhrkontrolle) — enforcement authority for LkSG
- **OECD NCP** — National Contact Point complaints under OECD Guidelines for Multinational Enterprises
- **NGO reports** — ECCHR, Germanwatch, Femnet e.V., and civil society organisations

---

## Project Structure

```
hades/
├── main.py                          # FastAPI entry point — loads .env, validates env vars
├── api/
│   └── routes.py                    # All API endpoints including audit + CSV export
├── agent/
│   ├── state.py                     # DDState TypedDict — full pipeline state schema
│   ├── graph.py                     # LangGraph StateGraph — fan-out/fan-in wiring
│   ├── prompts.py                   # SYNTHESIS_PROMPT, REPORT_PROMPT (Claude)
│   └── nodes/
│       ├── _utils.py                # parse_json_response() — shared JSON helper
│       ├── hermes_preflight.py      # Pre-flight: read Hermes Redis intel
│       ├── web_research.py          # 4 Serper queries, negative-signal flagging
│       ├── news_sentiment.py        # newsapi.ai — last 90 days, EN+DE
│       ├── sanctions_check.py       # OFAC SDN + UN SC XML, 24h in-memory cache
│       ├── registry_lookup.py       # NorthData + Unternehmensregister
│       ├── lksg_signals.py          # BAFA, NCP, ECCHR/NGO signals
│       ├── esg_signals.py           # EcoVadis, ILO, TI, Violation Tracker
│       ├── synthesis.py             # Claude Sonnet 4.6: score 6 risk dimensions
│       ├── report_generator.py      # Claude Sonnet 4.6: full structured DD report
│       ├── hermes_register.py       # Post-report: write supplier to Hermes watchlist
│       └── audit_writer.py          # Post-report: persist audit record to Redis
├── integrations/
│   ├── hermes_client.py             # Upstash Redis client — audit read/write + watchlist
│   └── serper_client.py             # Shared Serper search function
├── demo/
│   └── run_demo.py                  # 4-scenario live demo script
└── screenshots/                     # Demo screenshots
```

---

## Part of the SpendLens Stack

| Agent | Role | Trigger |
|---|---|---|
| **Icarus** | Personal AI OS — orchestrates everything from Telegram | User message |
| **SpendLens** | Spend analytics, vendor records, approval workflows | User-facing platform |
| **Hades** | Autonomous supplier due diligence — gates vendor onboarding | SpendLens onboarding + Icarus query |
| **Hermes** | Ongoing market intelligence — crawls signals, monitors watchlist | Scheduled / Hades registration |

Hades and Hermes share the same Upstash Redis instance. Every vendor Hades investigates is automatically added to the Hermes watchlist — so Hermes crawlers begin monitoring them from the next cycle. On subsequent rechecks, Hermes data is pre-loaded into the Hades risk score.
