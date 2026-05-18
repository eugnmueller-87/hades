# Hades — Supplier Due Diligence Agent

**Hades** is the gatekeeper of the SpendLens procurement stack. It autonomously researches any supplier and generates a structured due diligence report — covering sanctions, company registry, news sentiment, LkSG/CSDDD compliance, ESG signals, and live Hermes market intelligence — in under 2 minutes. No manual research. No spreadsheets.

> **SpendLens procurement stack:** Icarus (personal AI OS) · SpendLens (spend analytics) · **Hades** (supplier vetting) · Hermes (market intelligence)

**Live:** `https://hades-production-b86a.up.railway.app` · **[Project board](https://github.com/users/eugnmueller-87/projects/8/views/1)**

---

## Screenshot

![Hades — Bosch investigation, High risk, score 5.0, investigation pipeline complete](screenshots/Screenshot%202026-05-16%20205825.png)

---

## What Hades Does

Send a company name, category, and country. Hades runs 6 parallel research pipelines and returns a full structured risk report with:

- **Overall risk score** (1–10, weighted across 6 dimensions)
- **Recommendation**: `Approve` / `Conditional Approval` / `Block`
- **Executive summary** in plain language
- **Company registry details** — legal status and registration
- **Sanctions status** — OFAC SDN + UN SC Consolidated List
- **LkSG/CSDDD compliance signal** — no findings / needs monitoring / red flag
- **ESG & labour risk** — cross-referenced against major ESG databases
- **Required next steps** surfaced to the procurement manager
- **Hermes integration** — reads prior intelligence pre-flight, registers new suppliers post-report for ongoing monitoring
- **Persistent audit trail** — every investigation saved, queryable via API

### Risk Dimensions

| Dimension | Data Source |
|---|---|
| Sanctions & Watchlists | OFAC SDN XML + UN SC Consolidated List (free, no API key) |
| LkSG / CSDDD Compliance | BAFA, OECD NCP, ECCHR/NGO signals |
| Company Registry | NorthData + Unternehmensregister |
| News Sentiment | newsapi.ai — last 90 days |
| ESG & Labour | EcoVadis, ILO, Transparency Intl, Violation Tracker |
| Hermes Intelligence | Live SpendLens market signals |

---

## Internal Pipeline

```
POST /investigate
       │
  hermes_preflight          ← reads prior Hermes intelligence
       │
  ┌────┴──────────────────────────────────────────────┐
  │            parallel LangGraph fan-out             │
  │  web_research   news_sentiment   sanctions_check  │
  │  registry_lookup   lksg_signals   esg_signals     │
  └────────────────────────┬──────────────────────────┘
                           │
                       synthesis              ← Claude Sonnet 4.6
                           │
                   report_generator          ← Claude Sonnet 4.6
                           │
                   hermes_register           ← adds to Hermes watchlist
                           │
                    audit_writer             ← persists audit record
                           │
                          END
```

**Stack:** FastAPI · LangGraph StateGraph · Claude Sonnet 4.6 · Upstash Redis · Serper · newsapi.ai · OFAC SDN XML · UN SC XML

---

## API

### `POST /investigate`

Submit a company for due diligence. Returns a full structured risk report with overall score, recommendation, and per-dimension findings.

**Request fields:** company name, procurement category, country (ISO-2), mode (`full` or `recheck`)

### `GET /audit/{company}`

Returns the full investigation history for a supplier, newest first.

### `GET /audit/{company}/latest`

Returns only the most recent audit record.

### `GET /audit/export/csv`

Downloads the full audit history for all investigated suppliers as a CSV file.

### `GET /audit/{company}/export/csv`

Downloads the audit trail for a single supplier as a CSV file.

### `GET /health`

Service health check.

---

## Audit Trail

Every investigation is persisted to Upstash Redis. Audit data survives Railway redeployments and risk score changes are trackable over time. CSV export available for portfolio-level review.

---

## Icarus Integration (Telegram)

Icarus exposes Hades-related tools to the user via Telegram:

| Tool | Example prompts |
|---|---|
| Supplier lookup | "Is Bechtle a supplier?" · "Have we checked Siemens?" |
| DD report | "Pull the DD report for Bosch" · "What's the risk score for SAP?" |
| Audit history | "Show me the audit trail for Bechtle" |
| CSV export | "Export supplier report" · "Send me a CSV for Bechtle" |

---

## SpendLens Integration

When a new vendor is created in SpendLens, Hades runs a full investigation automatically. The recommendation (`Approve` / `Conditional Approval` / `Block`) gates the onboarding decision. Every investigated supplier is automatically added to the Hermes watchlist for ongoing monitoring.

---

## Setup

### Requirements

- Python 3.11+
- API keys: Anthropic, Serper.dev, newsapi.ai, Upstash Redis

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

All required environment variables are validated at startup.

---

## LkSG / CSDDD Context

The **Lieferkettensorgfaltspflichtengesetz (LkSG)** — German Supply Chain Due Diligence Act — has been in force since January 2023 for companies with 1,000+ employees. It mandates risk-based due diligence across the full supply chain: human rights, environmental obligations, and grievance mechanisms.

The EU **CSDDD** (Corporate Sustainability Due Diligence Directive) extends equivalent requirements across all EU member states from 2026.

Hades checks three authoritative sources for LkSG/CSDDD signals:

- **BAFA** (Bundesamt für Wirtschaft und Ausfuhrkontrolle) — enforcement authority for LkSG
- **OECD NCP** — National Contact Point complaints under OECD Guidelines for Multinational Enterprises
- **NGO reports** — ECCHR, Germanwatch, Femnet e.V., and civil society organisations

---

## Part of the SpendLens Stack

| Agent | Role |
|---|---|
| **Icarus** | Personal AI OS — orchestrates everything from Telegram |
| **SpendLens** | Spend analytics, vendor records, approval workflows |
| **Hades** | Autonomous supplier due diligence — gates vendor onboarding |
| **Hermes** | Ongoing market intelligence — crawls signals, monitors watchlist |
