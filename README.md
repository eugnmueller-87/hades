# Supplier Due Diligence Agent

Autonomous supplier research agent — generates structured Due Diligence Reports covering sanctions, company registry, news sentiment, LkSG/CSDDD compliance, and ESG signals. Integrates with Hermes for ongoing monitoring and SpendLens for vendor onboarding.

## Status

🚧 Under construction — see [ROADMAP.md](../ROADMAP.md) for build plan.

## Architecture

```
POST /investigate
  → Hermes pre-flight (existing signals?)
  → 6 parallel research nodes
  → Claude synthesis (6 risk dimensions)
  → Structured DD Report JSON
  → register_vendor() in Hermes
  → SpendLens Compliance Scorecard
```

## Tech Stack

- **FastAPI** — HTTP API
- **LangGraph** — agent orchestration
- **Claude Sonnet 4.6** — risk scoring + report generation
- **Serper.dev** — web research, LkSG/ESG signals
- **NewsAPI** — news sentiment (EN + DE)
- **OpenSanctions** — sanctions & watchlists (OFAC, EU, UN, UK + 100 datasets)
- **OpenCorporates** — company registry
- **Hermes** — ongoing supplier monitoring via Upstash Redis

## Legal Context

Covers supplier due diligence obligations under:
- **LkSG** (German Supply Chain Due Diligence Act, in force Jan 2023)
- **CSDDD** (EU Corporate Sustainability Due Diligence Directive, transposition 2026)
- **EU Forced Labour Regulation** (pending)

## Setup

```bash
git clone https://github.com/eugnmueller-87/supplier-dd-agent
cd supplier-dd-agent
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys
uvicorn main:app --reload
```
