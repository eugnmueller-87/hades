"""
4-Scenario Demo for Hades (Supplier Due Diligence Agent)
---------------------------------------------------------
Scenario 1: Clean DACH supplier, not in Hermes â†’ full research â†’ expected Low/Medium
Scenario 2: Supplier with known LkSG/ESG exposure â†’ expected High/Conditional
Scenario 3: Large sanctioned-adjacent entity â†’ expected Critical/Block indicators
Scenario 4: Re-check Scenario 1 supplier (now in Hermes) â†’ shows Hermes delta

Run with server live:
    .venv/Scripts/python.exe demo/run_demo.py
"""

import httpx
import json
import time

BASE_URL = "http://127.0.0.1:8000"

SCENARIOS = [
    {
        "id": 1,
        "label": "Clean DACH Supplier (new to Hermes)",
        "request": {"company": "Schindler Group", "category": "Facilities & Office", "country": "CH", "mode": "full"},
        "expect": "Low or Medium risk â€” no major flags expected",
    },
    {
        "id": 2,
        "label": "LkSG/ESG-exposed supplier",
        "request": {"company": "H&M Group", "category": "Facilities & Office", "country": "SE", "mode": "full"},
        "expect": "High risk â€” documented labour rights issues + ECCHR/NGO flags",
    },
    {
        "id": 3,
        "label": "High-risk entity with geopolitical exposure",
        "request": {"company": "Huawei Technologies", "category": "IT Software & SaaS", "country": "CN", "mode": "full"},
        "expect": "High or Critical â€” US export restrictions + sanctions adjacency",
    },
    {
        "id": 4,
        "label": "Re-check Scenario 1 supplier (now tracked in Hermes)",
        "request": {"company": "Schindler Group", "category": "Facilities & Office", "country": "CH", "mode": "recheck"},
        "expect": "Hermes shows tracked=True, monitoring_status shows prior registration",
    },
]


def _bar(score: float) -> str:
    filled = int(score)
    return "â–ˆ" * filled + "â–‘" * (10 - filled) + f"  {score}/10"


def run_scenario(scenario: dict) -> dict:
    print(f"\n{'='*70}")
    print(f"  SCENARIO {scenario['id']}: {scenario['label']}")
    print(f"  Expected: {scenario['expect']}")
    print(f"{'='*70}")
    print(f"  >> POST /investigate  {scenario['request']['company']} ({scenario['request']['country']})")

    t0 = time.time()
    resp = httpx.post(f"{BASE_URL}/investigate", json=scenario["request"], timeout=300)
    elapsed = round(time.time() - t0, 1)

    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code}: {resp.text[:300]}")
        return {}

    data = resp.json()
    report = data.get("report", {})
    scores = data.get("risk_scores", {}).get("scores", {})

    print(f"\n  Company        : {report.get('company')}")
    print(f"  Overall Score  : {_bar(report.get('overall_risk_score', 0))}")
    print(f"  Risk Level     : {report.get('risk_level')}")
    print(f"  Recommendation : {report.get('recommendation')}")
    print(f"  Time           : {elapsed}s")

    print(f"\n  --- Risk Breakdown ---")
    for dim, v in scores.items():
        label = dim.replace("_", " ").title().ljust(22)
        print(f"  {label}: {_bar(v['score'])}")

    hermes = report.get("hermes_intelligence", {})
    print(f"\n  --- Hermes Intelligence ---")
    print(f"  Tracked        : {hermes.get('tracked_by_hermes')}")
    print(f"  Signal count   : {hermes.get('signal_count')}")
    print(f"  Status         : {hermes.get('monitoring_status')}")

    lksg = report.get("lksg_csddd_assessment", {})
    print(f"\n  --- LkSG/CSDDD ---")
    print(f"  Signal         : {lksg.get('compliance_signal')}")
    print(f"  Flagged        : {lksg.get('flagged_count')}")

    print(f"\n  --- Executive Summary ---")
    summary = report.get("executive_summary", "")
    for line in [summary[i:i+68] for i in range(0, len(summary), 68)]:
        print(f"  {line}")

    if report.get("required_next_steps"):
        print(f"\n  --- Required Next Steps ---")
        for step in report["required_next_steps"]:
            print(f"  â€¢ {step[:70]}")

    print(f"\n  hermes_registered: {data.get('hermes_registered')}")
    return data


def main():
    print("\n" + "="*70)
    print("  HADES - SUPPLIER DUE DILIGENCE AGENT - 4-SCENARIO DEMO")
    print("  SpendLens x Hermes x Hades")
    print("="*70)

    # Health check
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=5)
        print(f"\n  Server: {health.json()['status'].upper()} â€” {BASE_URL}")
    except Exception as e:
        print(f"\n  ERROR: Server not reachable at {BASE_URL}: {e}")
        return

    results = []
    for scenario in SCENARIOS:
        result = run_scenario(scenario)
        results.append({"scenario": scenario["id"], "label": scenario["label"], "result": result})
        if scenario["id"] < len(SCENARIOS):
            print("\n  [waiting 3s before next scenario...]")
            time.sleep(3)

    print(f"\n\n{'='*70}")
    print("  DEMO COMPLETE â€” SUMMARY")
    print("="*70)
    for r in results:
        report = r["result"].get("report", {})
        print(f"  S{r['scenario']}: {r['label'][:40].ljust(40)} | "
              f"{str(report.get('overall_risk_score', '?')).ljust(4)} "
              f"{str(report.get('risk_level', '?')).ljust(10)} "
              f"{report.get('recommendation', '?')}")
    print()


if __name__ == "__main__":
    main()

