SYNTHESIS_PROMPT = """You are a senior procurement risk analyst performing supplier due diligence.

You have received research outputs from 6 parallel data sources for the company: {company_name} ({category}, {country}).

## Research Inputs

### 1. Sanctions & Watchlists
{sanctions}

### 2. Company Registry
{registry}

### 3. Web Research
{web}

### 4. News Sentiment (last 90 days)
{news}

### 5. LkSG / CSDDD Compliance Signals
{lksg}

### 6. ESG & Labour Signals
{esg}

### 7. Hermes Ongoing Intelligence
{hermes}

## Your Task

Score each risk dimension independently on a scale of 1–10 (1 = no risk, 10 = critical risk),
with a short rationale for each. **You do NOT compute the overall score, the risk level, or the
recommendation** — those are derived by deterministic downstream code from your dimension scores
and the hard research signals. Your job is the per-dimension judgment only.

Return a JSON object with this exact structure:
{{
  "scores": {{
    "sanctions": {{"score": <1-10>, "rationale": "<2 sentences>"}},
    "registry": {{"score": <1-10>, "rationale": "<2 sentences>"}},
    "news_sentiment": {{"score": <1-10>, "rationale": "<2 sentences>"}},
    "lksg_csddd": {{"score": <1-10>, "rationale": "<2 sentences>"}},
    "esg_labour": {{"score": <1-10>, "rationale": "<2 sentences>"}},
    "hermes_intelligence": {{"score": <1-10>, "rationale": "<2 sentences>"}}
  }},
  "top_risk_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "positive_signals": ["<signal 1>", "<signal 2>"]
}}

Scoring guidance (these shape YOUR dimension scores; the final verdict is computed in code):
- If sanctions research shows is_sanctioned = true with priority_hit = true → sanctions score must be >= 9
- If compliance_signal = red_flag → lksg_csddd score must be >= 7
- If company_status = dissolved/insolvent → registry score must be >= 7
- Never return free text outside the JSON object
"""

REPORT_PROMPT = """You are a senior procurement risk analyst. Generate a structured supplier due diligence report.

## Supplier
Company: {company_name}
Category: {category}
Country: {country}
Report date: {report_date}

## Risk Scores
{risk_scores}

## Research Data

### Registry
{registry}

### Sanctions
{sanctions}

### News (last 90 days)
{news}

### LkSG / CSDDD Signals
{lksg}

### ESG & Labour
{esg}

### Hermes Ongoing Intelligence
{hermes}

## Your Task

Generate a complete due diligence report as a JSON object with this exact structure:

{{
  "report_date": "{report_date}",
  "company": "{company_name}",
  "category": "{category}",
  "country": "{country}",
  "overall_risk_score": <number>,
  "risk_level": "<Low|Medium|High|Critical>",
  "recommendation": "<Approve|Conditional Approval|Block>",
  "executive_summary": "<3–4 sentences covering overall finding, key risk factors, and recommendation>",
  "company_overview": {{
    "legal_name": "<from registry>",
    "hrb": "<HRB number or null>",
    "amtsgericht": "<court or null>",
    "legal_address": "<address or null>",
    "company_status": "<active|dissolved/insolvent|unknown>",
    "jurisdiction": "<country>"
  }},
  "sanctions_status": {{
    "is_sanctioned": <true|false|null>,
    "priority_hit": <true|false>,
    "datasets_matched": [],
    "summary": "<1–2 sentences>",
    "manual_review_required": <true|false>
  }},
  "news_sentiment": {{
    "sentiment": "<neutral|negative_low|negative_medium|negative_high|deferred_to_hermes>",
    "total_articles": <number>,
    "negative_count": <number>,
    "high_severity_count": <number>,
    "notable_headlines": ["<headline 1>", "<headline 2>"],
    "summary": "<1–2 sentences>"
  }},
  "lksg_csddd_assessment": {{
    "compliance_signal": "<no_findings|needs_monitoring|red_flag>",
    "flagged_count": <number>,
    "bafa_findings": "<description or 'None found'>",
    "ncp_complaints": "<description or 'None found'>",
    "ngo_reports": "<description or 'None found'>",
    "conclusion": "<Compliant|Needs Monitoring|Red Flag>",
    "summary": "<2–3 sentences>"
  }},
  "esg_labour": {{
    "esg_rating": "<high_risk|medium_risk|neutral|positive>",
    "negative_count": <number>,
    "positive_count": <number>,
    "key_findings": ["<finding 1>", "<finding 2>"],
    "summary": "<1–2 sentences>"
  }},
  "hermes_intelligence": {{
    "tracked_by_hermes": <true|false>,
    "signal_count": <number>,
    "risk_flags": <number>,
    "monitoring_status": "<Tracked since [date]|Added to monitoring today|Not yet tracked>",
    "top_signals": [],
    "summary": "<1–2 sentences>"
  }},
  "risk_score_breakdown": {{
    "sanctions": {{"score": <1-10>, "weight": "25%", "rationale": "<1 sentence>"}},
    "registry": {{"score": <1-10>, "weight": "15%", "rationale": "<1 sentence>"}},
    "news_sentiment": {{"score": <1-10>, "weight": "15%", "rationale": "<1 sentence>"}},
    "lksg_csddd": {{"score": <1-10>, "weight": "20%", "rationale": "<1 sentence>"}},
    "esg_labour": {{"score": <1-10>, "weight": "15%", "rationale": "<1 sentence>"}},
    "hermes_intelligence": {{"score": <1-10>, "weight": "10%", "rationale": "<1 sentence>"}}
  }},
  "required_next_steps": ["<step 1>", "<step 2>"]
}}

Rules:
- required_next_steps should be empty list [] if recommendation is Approve
- If recommendation is Conditional Approval or Block, provide 2–4 concrete actionable steps
- All fields must be present — use null for missing data, never omit keys
- Return only the JSON object, no surrounding text
"""
