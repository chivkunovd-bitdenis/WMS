## Summary

- Восстанавливает обязательные backend и browser release-гейты на текущем `etalon`.
- Убирает `MissingGreenlet` в обычных marketplace-unload коробах без возврата тяжёлой загрузки
  в scan path.
- Делает cleanup тестовых FBS-заказов fail-closed и сохраняет FBS QR/стикеры без изменения.
- Синхронизирует OpenAPI и Playwright-проверки с уже действующим production-контрактом/UI.

## Product gate

- [x] BA feature card оформлена как наряд и контракт восстановления гейта
- [x] `BA_READY` подтверждён зафиксированными границами и запретом менять FBS QR/форматы
- [x] `PRODUCT_APPROVED_FOR_DEV` дан владельцем прямой командой довести безопасно до прода
- [ ] BA/Product до разработки не были отдельными агентами: это repair-гейт без изменения экрана
- [x] Разработка и диагностика выполнялись изолированными агентами в отдельном worktree
- [x] `CODE_REVIEW_PASSED` получен после исправления двух найденных ослаблений Playwright
- [x] `PRODUCT_BROWSER_APPROVED` получен отдельным ux-judge в реальной видимой вкладке
- [x] Rework повторно прошёл targeted-тесты, reviewer и полный browser gate
- [x] Emergency bypass не использован

Product evidence:

```yaml
feature_cards_path: tasks/20260827-release-gate-repair/NARYAD.md, tasks/20260827-release-gate-repair/CONTRACT.md
feature_ids: release-gate-repair-20260827
ba_agents: root (наряд и контракт; repair без изменения production UI)
product_agents_before_dev: владелец продукта, прямая авторизация repair
dev_agents: gate_static_fix, gate_pytest_fix, root
code_review_agents: gate_repair_review
product_browser_agents_after_dev: release_browser_judge_retry
environment_url: http://127.0.0.1:5190 (API 18101, изолированная временная БД)
roles: диагностика, разработка, reviewer, ux-judge
actions_clicked: вход FF; FBS; Остатки WB; Упаковка; очередь маркировки
visible_states: FF shell; таблицы, фильтры, вкладки и пустые состояния; без seller shell
evidence_paths: docs/evidence/20260827-release-gate-repair/, tasks/20260827-release-gate-repair/EVIDENCE.md
verdicts:
  ba: BA_READY
  product_before_dev: PRODUCT_APPROVED_FOR_DEV
  code_review: CODE_REVIEW_PASSED
  product_browser_after_dev: PRODUCT_BROWSER_APPROVED
emergency_bypass: no
```

### Test coverage

| TC-ID | Applies | Notes |
|---|---|---|
| TC-GATE-FBS-001 | Y | Дано: действующие FBS заказы, поставки и WB QR. Когда: проходит полный backend и browser suite. Тогда: форматы `FBS-*`, получение и печать QR коробов и поставки остаются прежними; negative: внутренний обычный короб не подменяет официальный WB QR. |
| TC-GATE-BOX-002 | Y | Дано: marketplace unload с лениво загружаемыми строками. Когда: оператор открывает подбор, сохраняет распределение, копирует или удаляет короб. Тогда: нет `MissingGreenlet`, а scan path не получает тяжёлую загрузку всего документа; restriction: остатки и резервы не меняются вне операции. |
| TC-GATE-E2E-003 | Y | Given: current production UI and FF/seller route boundaries. When: full Playwright and visible-browser flows run. Then: current screens, product FBS limit PATCH/readback and exact access-denied messages are verified; expected: no weakened OR assertion and no missing product-level publication coverage. |

Негативные сценарии отдельно проверяют недопустимый cleanup без явных флагов, чужой tenant,
невалидный FBS limit, запрет прямых FF-маршрутов и сбой внешнего API. Ограничение: cleanup в
destructive-режиме на реальной БД не запускался; все данные тестов находились в изолированной БД.

## Test plan

- [x] `ruff check .` — pass
- [x] `mypy .` — pass, 306 files
- [x] `pytest` — 1031 passed, 5 skipped
- [x] `npm run build` — pass
- [x] `CI=1 npm run test:e2e` — 201 passed, 7 skipped

## Notes / risks

- `frontend/src` не менялся.
- Полный `npm run lint` не является CI-гейтом и остаётся красным на унаследованном долге вне
  границ этой задачи; обязательный `npm run build` зелёный.
