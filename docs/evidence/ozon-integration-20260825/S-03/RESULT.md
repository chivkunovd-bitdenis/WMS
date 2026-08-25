# S-03 local verification

- `pytest backend/tests/test_fbs_ozon_lane.py backend/tests/test_marketplace_foundation.py backend/tests/test_fbs_worklist_query_count.py -q` — 22 passed.
- `npm run test:unit -- --run src/screens/v2/fbsApi.test.ts src/screens/v2/FfFbsSupplyWorkspace.test.ts src/screens/v2/FbsSupplyCreateDialog.test.ts` — 9 passed.
- `npx tsc --noEmit -p tsconfig.app.json` and `npm run build` — exit 0.
- `ruff check --ignore RUF100` on changed backend files — exit 0. The repository's ordinary `ruff` also reports three pre-existing unused file-level `noqa` directives outside this slice.
- Browser evidence is not recorded: the in-app Browser binding is unavailable because its installed package has no required `browser-client.mjs`; the started local Playwright run did not reach an exit code before the command window elapsed.

No live Ozon request or stock mutation was made.
