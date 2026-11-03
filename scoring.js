// scoring.js: a line-by-line port of agent/scoring.py (hades, master), the deterministic
// decider. The model scores six research dimensions 1 to 10; this code alone computes the
// weighted score, the risk band, the recommendation and the hard overrides.
// Checked against the Python original on random inputs before publishing.
(function (root) {
  var WEIGHTS = {
    sanctions: 0.25,
    registry: 0.15,
    news_sentiment: 0.15,
    lksg_csddd: 0.20,
    esg_labour: 0.15,
    hermes_intelligence: 0.10,
  };

  // Low: 1.0 <= S < 4.0 · Medium: 4.0 <= S < 6.5 · High: 6.5 <= S < 8.0 · Critical: 8.0 <= S <= 10.0
  var BANDS = [[8.0, "Critical"], [6.5, "High"], [4.0, "Medium"], [0.0, "Low"]];

  var BAND_RECOMMENDATION = {
    Low: "Approve",
    Medium: "Conditional Approval",
    High: "Conditional Approval",
    Critical: "Block",
  };

  var REC_SEVERITY = { "Approve": 0, "Conditional Approval": 1, "Block": 2 };

  function clampScore(v) {
    var f = typeof v === "number" ? v : parseFloat(v);
    if (v === null || v === undefined || v === "" || isNaN(f)) return 5.0;
    return Math.max(1.0, Math.min(10.0, f));
  }

  // Python's round(x, 1): rounds the exact binary value, ties to even.
  function round1(x) {
    var exact = x.toFixed(60);
    var dot = exact.indexOf(".");
    var tenths = exact.charAt(dot + 1);
    if (/^50*$/.test(exact.slice(dot + 2))) {
      var down = Number(exact.slice(0, dot + 2));
      return Number(tenths) % 2 === 0 ? down : Number((down + 0.1).toFixed(1));
    }
    return Number(x.toFixed(1));
  }

  function weightedOverall(scores) {
    var total = 0.0;
    Object.keys(WEIGHTS).forEach(function (dim) {
      var raw = scores[dim];
      var s = clampScore(raw !== null && typeof raw === "object" ? raw.score : raw);
      total += s * WEIGHTS[dim];
    });
    return round1(total);
  }

  function bandFor(overall) {
    for (var i = 0; i < BANDS.length; i++) if (overall >= BANDS[i][0]) return BANDS[i][1];
    return "Low";
  }

  function escalate(current, target) {
    return REC_SEVERITY[target] > REC_SEVERITY[current] ? target : current;
  }

  function applyOverrides(recommendation, scores, signals) {
    var rec = recommendation;
    var reasons = [];

    if (signals.is_sanctioned && signals.priority_hit) {
      rec = escalate(rec, "Block");
      reasons.push("Sanctions: confirmed priority watchlist hit → Block");
    }

    var status = (signals.company_status || "").toLowerCase();
    if (status === "dissolved" || status === "insolvent" || status === "dissolved/insolvent") {
      rec = escalate(rec, "Conditional Approval");
      reasons.push("Registry: company status '" + status + "' → at least Conditional");
    }

    if ((signals.compliance_signal || "").toLowerCase() === "red_flag") {
      rec = escalate(rec, "Conditional Approval");
      reasons.push("LkSG/CSDDD: red flag → at least Conditional");
    }

    var sanc = scores.sanctions;
    var sancScore = clampScore(sanc !== null && typeof sanc === "object" ? sanc.score : sanc);
    if (sancScore >= 9.0) {
      rec = escalate(rec, "Conditional Approval");
      reasons.push("Sanctions dimension score >= 9 → at least Conditional");
    }

    if (signals.sanctions_degraded || signals.manual_review_required) {
      rec = escalate(rec, "Conditional Approval");
      var unavailable = signals.sources_unavailable || [];
      var detail = unavailable.length ? " (unverified: " + unavailable.join(", ") + ")" : "";
      reasons.push("Sanctions screen degraded/unverified → at least Conditional (manual review)" + detail);
    }

    return [rec, reasons];
  }

  function decide(scores, signals) {
    signals = signals || {};
    var overall = weightedOverall(scores);
    var band = bandFor(overall);
    var out = applyOverrides(BAND_RECOMMENDATION[band], scores, signals);
    return {
      overall_risk_score: overall,
      risk_level: band,
      recommendation: out[0],
      override_reasons: out[1],
      _decided_by: "deterministic",
    };
  }

  var api = { WEIGHTS: WEIGHTS, decide: decide, weightedOverall: weightedOverall, bandFor: bandFor };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HadesScoring = api;
})(this);
