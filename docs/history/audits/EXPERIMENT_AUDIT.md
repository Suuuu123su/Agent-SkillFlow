# T17 Experiment Audit

**Verdict: WARN_INCOMPLETE.** T17-A–D have valid evidence; T17-E is incomplete; T17-F–H were not run.

| Check | Status | Evidence |
|---|---|---|
| Raw Attempt preservation | PASS | runs/t17-live-20260902-01..05 retained |
| Cross-Attempt pooling | PASS | Attempts reported separately |
| Scripted Golden independence | PASS | Expectations are stored independently |
| Phantom results | PASS | F/G/H remain not_available |
| Numerator/denominator retention | PASS | JSON and CSV retain raw counts |
| Live scope | WARN | T17-E scheduled denominator incomplete |
| Final full test | WARN | Not rerun after final Live fixes per user instruction |
| Independent final reviewer | REVIEW_UNAVAILABLE | Reviewer-model independence cannot be proven |

## Claim Boundary

Do not claim T17 completion, Model1 formal results, Model2 results, cross-model agreement, or Defense Security Gain. Cost values are engineering estimates rather than confirmed billing.

## Evidence

- docs/evidence/t17-final-metrics.json
- docs/evidence/t17-final-summary.csv
- docs/evidence/t17-e-canary-partial-audit.json
- docs/evidence/t17-scripted-golden-summary-v2.json
