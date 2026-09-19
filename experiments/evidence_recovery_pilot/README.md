# Evidence recovery pilot

Offline, standard-library-only experiments using the archived P4 observation
projection and predictor. No model, network, or business action is executed.
The historical P4 archive and code remain unchanged.

- `run.py prepare` writes the frozen 240-query plan before prediction.
- `run.py run` validates all frozen hashes and evaluates the plan.
- `reference_check.py prepare` writes a separate, explicitly post-pilot plan for
  all 235 controlled-construct queries in the same five-metric scope.
- `reference_check.py run` runs that extension without changing any acquisition
  policy, priority, seed or budget.
- `report.py [--out PATH]` produces descriptive reports and checks consistent
  samples, identical initial states, agreement at maximal recovery, and errors
  against independent finite references. It accepts plain or gzip CSV.

Run from the repository root; outputs default to:

- [Main pilot](../../论文材料/修复与补强_20260919/evidence_pilot/README.md)
- [Finite-reference extension](../../论文材料/修复与补强_20260919/evidence_pilot_reference/README.md)

Both runs completed with zero analysis errors. The adaptive rule did not improve
aggregate point coverage over the strong metric-specific fixed order. Its
missing-field feedback does not capture every nested cross-channel dependency.
This negative result is retained. Full agreement is distinct from independent
truth; finite-reference selective accuracy is always reported with coverage.

`PLAN.json` and `PLAN.sha256` are immutable execution records. Use a fresh `--out`
directory for new preparation. Budget/policy/seed rows are repeated observations,
not additional independent tasks. Family count and JSON byte growth are offline
cost proxies, not measured collector latency or cost. Existing semantic gaps
remain unknown rather than being filled with reference labels.
