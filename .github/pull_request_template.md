## Summary
- 

## Pipeline v2 status

Целевой процесс: `docs/process/PIPELINE-RU.md`. Машинный статус/hash:
`pipeline/pipeline.yml`. Пока статус не `ACTIVE`, PR обязан
заполнять старый Product gate ниже; Pipeline v2 нельзя считать активированным без
owner approval и зелёных метатестов части XII.

## Product gate

Обязательно для любой WMS-задачи. См. `AGENTS.md`,
`docs/WMS_FEATURE_GATE_PROTOCOL_RU.md` и `docs/WMS_PRODUCT_AGENT_RU.md`.

- [ ] BA feature cards созданы для каждой карточки
- [ ] `BA_READY` есть для каждой карточки
- [ ] `PRODUCT_APPROVED_FOR_DEV` получен до разработки
- [ ] Каждая роль выполнялась отдельным изолированным агентом
- [ ] `CODE_REVIEW_PASSED` получен после разработки
- [ ] `PRODUCT_BROWSER_APPROVED` получен после разработки в реальной видимой вкладке браузера
- [ ] Rework, если был, повторно прошел BA/Product/Dev/Review/Product Browser
- [ ] Emergency bypass не использован или явно одобрен пользователем

Product evidence:

```yaml
feature_cards_path:
feature_ids:
ba_agents:
product_agents_before_dev:
dev_agents:
code_review_agents:
product_browser_agents_after_dev:
environment_url:
roles:
actions_clicked:
visible_states:
evidence_paths:
verdicts:
  ba:
  product_before_dev:
  code_review:
  product_browser_after_dev:
emergency_bypass:
```

## Test coverage

Обязательно для PR, который трогает `frontend/src`, `frontend/tests-e2e`, `backend/app/api` или `backend/app/services` (см. `AGENTS.md`). Label **`skip-test-coverage-check`** отключает только TC-таблицу и только по согласованию; Product gate он не отключает.

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
