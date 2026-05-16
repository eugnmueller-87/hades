# Supplier Due Diligence Agent

An autonomous AI agent that researches any company and generates a structured procurement due diligence report — covering sanctions, company registry, news sentiment, LkSG/CSDDD compliance, ESG signals, and Hermes ongoing intelligence — in under 2 minutes.

Built as a standalone module for the **SpendLens** procurement intelligence platform.

---

## What it does

`POST /investigate` with a company name, category, and country returns a full structured DD report with:

- **Risk score** across 6 dimensions (1-10 each, weighted overall)
- **Recommendation**: Approve / Conditional Approval / Block
- **Executive summary** in plain language
- **Required next steps** when risk is elevated
- **Hermes integration**: reads prior intelligence pre-flight, registers new suppliers post-report

### Risk dimensions

| Dimension | Weight | Source |
|---|---|---|
| Sanctions & Watchlists | 25% | OpenSanctions matching API |
| LkSG / CSDDD Compliance | 20% | BAFA, NCP, ECCHR/NGO (via Serper) |
| Company Registry | 15% | NorthData, Unternehmensregister (via Serper) |
| News Sentiment | 15% | newsapi.ai (Event Registry) - last 90 days |
| ESG & Labour | 15% | EcoVadis, ILO, Transparency Intl, Violation Tracker |
| Hermes Intelligence | 10% | Upstash Redis - SpendLens market signals |

---

## Architecture

```
POST /investigate
       |
  hermes_preflight          <- reads Hermes Redis; skips news if signal_count > 10
       |
  +----+------------------------------------------+
  | (parallel LangGraph fan-out)                  |
  web_research   news_sentiment   sanctions_check  |
  registry_lookup   lksg_signals   esg_signals    |
  +--------------------+--------------------------+
                       |
                   synthesis                       <- Claude Sonnet 4.6: scores 6 dims
                       |
               report_generator                   <- Claude Sonnet 4.6: full JSON report
                       |
               hermes_register                    <- writes new supplier to Hermes watchlist
                       |
                     END
```

**Stack**: FastAPI - LangGraph (StateGraph) - Claude Sonnet 4.6 - Upstash Redis - Serper - newsapi.ai - OpenSanctions

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

**Response** (abbreviated):

```json
{
  "company": "Robert Bosch GmbH",
  "report": {
    "overall_risk_score": 4.7,
    "risk_level": "Medium",
    "recommendation": "Conditional Approval",
    "executive_summary": "...",
    "company_overview": { "hrb": "HRB 14000", "amtsgericht": "Amtsgericht Stuttgart" },
    "sanctions_status": { "is_sanctioned": null, "manual_review_required": true },
    "lksg_csddd_assessment": { "compliance_signal": "red_flag", "flagged_count": 12 },
    "esg_labour": { "esg_rating": "high_risk" },
    "hermes_intelligence": { "tracked_by_hermes": false, "monitoring_status": "Added to monitoring today" },
    "required_next_steps": ["...", "..."]
  },
  "hermes_registered": true
}
```

### `GET /health`

```json
{ "status": "ok", "agent": "supplier-dd-agent", "version": "0.1.0" }
```

---

## Hermes read/write flow

```
Pre-flight:  get_vendor_intel(company)  -> if tracked + signal_count > 10 -> skip NewsAPI
Post-report: register_vendor(company)   -> idempotent; adds to Hermes watchlist for crawlers
```

The agent always runs sanctions, registry, and LkSG checks at full depth regardless of Hermes coverage.

---

## Demo scenarios

Run `demo/run_demo.py` with the server live. Results from live run:

| Scenario | Company | Score | Risk | Recommendation |
|---|---|---|---|---|
| Clean DACH supplier (new) | Schindler Group (CH) | 5/10 | Medium | Conditional Approval |
| LkSG/ESG-exposed | H&M Group (SE) | 6/10 | High | Conditional Approval |
| Geopolitical + sanctions risk | Huawei Technologies (CN) | 7/10 | High | **Block** |
| Re-check (Hermes delta) | Schindler Group (CH) | 4/10 | Medium | Conditional Approval |

---

## Setup

### Requirements

- Python 3.11+
- API keys: Anthropic, Serper.dev, newsapi.ai (Event Registry), OpenSanctions, Upstash Redis

### Local run

```bash
git clone https://github.com/eugnmueller-87/supplier-dd-agent.git
cd supplier-dd-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your API keys
uvicorn main:app --reload
```

Then:

```bash
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -d '{"company": "Siemens AG", "category": "Electronics", "country": "DE"}'
```

### Environment variables

See [`.env.example`](.env.example) for all required variables.

---

## Project structure

```
supplier-dd-agent/
+-- main.py                          # FastAPI entry point (loads .env)
+-- api/routes.py                    # POST /investigate, GET /health
+-- agent/
|   +-- state.py                     # DDState TypedDict
|   +-- graph.py                     # LangGraph StateGraph
|   +-- prompts.py                   # SYNTHESIS_PROMPT, REPORT_PROMPT
|   +-- nodes/
|       +-- hermes_preflight.py      # Read Hermes pre-flight
|       +-- web_research.py          # Serper web research
|       +-- news_sentiment.py        # newsapi.ai 90-day sentiment
|       +-- sanctions_check.py       # OpenSanctions matching API
|       +-- registry_lookup.py       # NorthData / Handelsregister
|       +-- lksg_signals.py          # BAFA, NCP, ECCHR/NGO signals
|       +-- esg_signals.py           # EcoVadis, ILO, TI, labour
|       +-- synthesis.py             # Claude: risk scoring
|       +-- report_generator.py      # Claude: full DD report
|       +-- hermes_register.py       # Write supplier to Hermes
+-- integrations/
|   +-- hermes_client.py             # Upstash Redis client
|   +-- spendlens_connector.py       # SpendLens integration stub
+-- demo/run_demo.py                 # 4-scenario live demo
```

---

## LkSG / CSDDD context

The **Lieferkettensorgfaltspflichtengesetz (LkSG)** - German Supply Chain Due Diligence Act - has been in force since January 2023. It requires companies with 1,000+ employees to conduct risk-based due diligence across their full supply chain, including human rights and environmental obligations.

The EU **CSDDD** (Corporate Sustainability Due Diligence Directive) extends similar requirements across the EU from 2026. This agent specifically checks:

- **BAFA** (Bundesamt fuer Wirtschaft und Ausfuhrkontrolle) - the German enforcement authority for LkSG
- **OECD NCP** - National Contact Point complaints under OECD Guidelines for Multinational Enterprises
- **NGO reports** - ECCHR, Germanwatch, Femnet e.V., and similar civil society organisations

---

## Part of SpendLens

This agent is a module of the **SpendLens** procurement intelligence stack:

- **SpendLens** - AI spend analysis and vendor categorisation
- **Hermes** - ongoing market intelligence and signal monitoring
- **Supplier DD Agent** - autonomous supplier due diligence (this repo)
