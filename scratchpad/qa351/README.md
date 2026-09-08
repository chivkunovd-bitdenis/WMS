# WMS-351 isolated acceptance

Production base: `6b1bd3d8faf41768f9d962335778a8869d73ef7b` (includes WMS-393).
Only local PostgreSQL and fake marketplace transports. Runtime rejects non-loopback
socket connections; no real marketplace credentials/accounts are used.

Start from this worktree with the shared backend virtualenv:

```sh
createdb wms351_browser_6b1
python scratchpad/qa351/seed.py
cd scratchpad/qa351
uvicorn runtime:app --host 127.0.0.1 --port 18551
```

In frontend: `VITE_API_PROXY=http://127.0.0.1:18551 npm run dev -- --host 127.0.0.1 --port 15551`.
Sign in at http://127.0.0.1:15551 with `qa351@example.com` / `password123`.
Seed refuses to overwrite an existing database. IDs are written to local `baseline.json`.
`external.jsonl` records fake publication requests, `blocked-network.jsonl` records
rejected external sockets. These data/log files are not committed.

Manual Safari acceptance on 08.09.2026: catalog → select synthetic product →
«Задать остаток» → inspect two publication checkboxes and two served warehouse controls.
Baseline: both enabled, legacy Ozon NULL, 10 physical, 50% each.
After fake service baseline publication (WB5 + Ozon5):

- WB off → save → reopen: WB false/Ozon true. Only WB PUT0 + readback.
- WB on, Ozon off → save → reopen: WB true/Ozon false. Only Ozon0 and WB5 + readback.
- Save unchanged again: no additional requests.
- With final touched-checkbox API patch, enable only Ozon → save: one Ozon5 request,
  no WB request. Database both true, physical quantity still 10; both served unchanged.

PostgreSQL concurrency acceptance uses a DIFFERENT disposable database:

```sh
createdb wms351_pg_tests
cd backend
WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms351_pg_tests pytest -q -n 0 tests/test_wms351_publication_concurrency.py
```

Those tests intentionally rebuild only the named test database through the existing
pytest fixtures. They verify manual publication cannot race between final zero and
off commit, and an older ORM object cannot skip final zero after a concurrent enable.
