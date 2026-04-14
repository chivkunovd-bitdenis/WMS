## Summary
- 

## Test coverage

Обязательно для PR, который трогает `frontend/src`, `frontend/tests-e2e`, `backend/app/api` или `backend/app/services` (см. `AGENTS.md`). Исключение: label **`skip-test-coverage-check`** (только по согласованию).

Скопируйте из issue блок `### Test coverage` (таблица TC-ID) или заполните здесь. **Notes** — не пусто: Given/When/Then (или дано/когда/тогда), негативы/ограничения, ожидаемый вид UI; иначе CI отсечёт короткий «формализм» (`AGENTS.md` → Quality bar).

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|-----------------|---------------|-------|
|  |  |  |  |

## Test plan
- [ ] `ruff check .` (backend)
- [ ] `mypy .` (backend)
- [ ] `pytest` (backend)
- [ ] `npm run build` (frontend)
- [ ] `npm run test:e2e` (frontend)

## Notes / risks
- 

