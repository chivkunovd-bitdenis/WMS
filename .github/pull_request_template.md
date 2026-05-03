## Summary
- 

## Test coverage

Обязательно для PR, который трогает `frontend/src`, `frontend/tests-e2e`, `backend/app/api` или `backend/app/services` (см. `AGENTS.md`). Исключение: label **`skip-test-coverage-check`** (только по согласованию).

Скопируйте из issue блок `### Test coverage` (таблица TC-ID) или заполните здесь. **Notes** — не пусто: Given/When/Then (или дано/когда/тогда), негативы/ограничения, ожидаемый вид UI; иначе CI отсечёт короткий «формализм» (`AGENTS.md` → Quality bar).

**Порог CI** (`scripts/ci/check_pr_test_coverage.py`): в **описании** PR добавьте отдельным блоком заголовок ровно `### Test coverage` (три решётки); внутри секции не меньше **двух** строк таблицы с `TC-...`, хотя бы одна с **Y** в колонке Applies; суммарно секция не короче **~400 символов**; в тексте (таблица + абзацы под ней) встречаются **не меньше трёх** разных маркеров из набора: given / when / then, дано / когда / тогда, negative / негатив, restriction / огранич, expected / ожидаемо.

## Test plan
- [ ] `ruff check .` (backend)
- [ ] `mypy .` (backend)
- [ ] `pytest` (backend)
- [ ] `npm run build` (frontend)
- [ ] `npm run test:e2e` (frontend)

## Notes / risks
- 

