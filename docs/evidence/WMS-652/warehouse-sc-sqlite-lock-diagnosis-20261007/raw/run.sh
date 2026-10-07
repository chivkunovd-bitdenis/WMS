#!/usr/bin/env bash
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "$(uname -s)" == Linux ]]
python -c 'import sys; assert sys.version_info[:2] == (3,11)'
[[ -z "${WMS_TEST_DATABASE_URL:-}" ]]
export WMS652_SQLITE_EVIDENCE="${RUNNER_TEMP:?}/wms652-warehouse-sc-sqlite"
mkdir -p "$WMS652_SQLITE_EVIDENCE"
python --version > "$WMS652_SQLITE_EVIDENCE/environment.txt"
uname -a >> "$WMS652_SQLITE_EVIDENCE/environment.txt"
cat /etc/os-release >> "$WMS652_SQLITE_EVIDENCE/environment.txt"
python -m pip freeze > "$WMS652_SQLITE_EVIDENCE/dependencies.txt"
git rev-parse HEAD > "$WMS652_SQLITE_EVIDENCE/source-sha.txt"
git diff --exit-code cbd126200788b87d1a006c5853d8e9560148cd36 -- backend wb_emulator
git ls-files backend wb_emulator | xargs sha256sum > "$WMS652_SQLITE_EVIDENCE/protected-before.sha256"
cp scripts/ci/warehouse-sc-diagnostic/wms652_sqlite_observer.py "$WMS652_SQLITE_EVIDENCE/"
export PYTHONPATH="$PWD/scripts/ci/warehouse-sc-diagnostic${PYTHONPATH:+:$PYTHONPATH}"
set +e
(cd backend && timeout 180s python -m pytest -n 1 -q -s -p wms652_sqlite_observer tests/test_fbs_operator_flow_handoff.py::test_full_flow_warehouse_sc_emulator --junitxml="$WMS652_SQLITE_EVIDENCE/selected.xml") > "$WMS652_SQLITE_EVIDENCE/selected.log" 2>&1
result=$?
set -e
git ls-files backend wb_emulator | xargs sha256sum > "$WMS652_SQLITE_EVIDENCE/protected-after.sha256"
cmp "$WMS652_SQLITE_EVIDENCE/protected-before.sha256" "$WMS652_SQLITE_EVIDENCE/protected-after.sha256"
printf '{"selected_exit":%s}\n' "$result" > "$WMS652_SQLITE_EVIDENCE/exit-results.json"
cat "$WMS652_SQLITE_EVIDENCE/selected.log"
exit "$result"
