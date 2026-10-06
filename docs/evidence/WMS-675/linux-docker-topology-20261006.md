# WMS-675: isolated Linux/Docker topology verification

The previously failing setup guard now passes on the exact common product source `585877bedf948faf7e38d14acc7e89acbf4feab3`. No test, runtime or database safety guard was changed.

- Workflow source: `457da6040009d6ed36339c6e243b17db62e00e50`, branch `codex/wms675-ci-topology-proof-20261006`.
- Actual GitHub run: [37474405993](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37474405993), completed SUCCESS; job `112305945505`.
- Command: `pytest -n 0 -q -s tests/test_wms675_recovery_scenario.py`. Exactly one case, PASS in 3.58 seconds; no skip.
- Frozen test blob: `42f0b465dc4f08d50041b3db245eaa60fda46fe1`.
- Actual server identity printed by the frozen test: `wms_test_675_incident 172.18.0.2:5432`.
- URL hostname `postgres` is mapped to the runner's published loopback service `127.0.0.1:5432`; the step first asserts DNS addresses equal exactly `{'127.0.0.1'}`. The original Docker-aware guard is unchanged.

The PostgreSQL service definition and entire incident675 step match the common585 workflow objects. Setup uses Python3.11 and the existing backend `pip install -e ".[dev]"` dependency command. Only this incident case runs; no frontend, full SQLite, other PostgreSQL test or migration step runs. The proof workflow is restricted to its exact proof branch and workflow path. It checks out the immutable common585 source, rather than running product code from the proof commit.

The earlier isolated proof37474157320 stopped before the test because its install command incorrectly assumed requirements.txt. That command was corrected to the project's existing pyproject installation; the failed attempt is not counted as a test result. CI5 `37473872680` was cancelled after the owner's new restriction; its incomplete jobs do not establish readiness. The previous CI4 frontend/guards/backlog PASS remain separate facts.

This PASS proves the intended Linux runner/Docker address topology and the existing incident assertions (26 accounted,5 excluded,reserve16→1,facts11→26,charges22→52,replay0). It does not prove completion of the full backend/migration CI or staging deployment. Main, production and actual client675 accounting remain untouched. The common branch remains on585 until further instruction.
