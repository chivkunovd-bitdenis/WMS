# S0R Call 19 — отрицательный вердикт ведущего

**Дата:** 24 августа 2026 года

**Baseline:** `cd17496dbf955c7fd4b02cb3c6a9f9baafc4cc31`

**Результат:** `PRODUCT_REJECTED`. Незакоммиченный diff Call 19 технически собирается, но не выполняет binding contract `S0R_REWORK_CONTRACT.md` и не допускается к browser approval.

## Названные находки

1. **CAT-19-01 — действие каталога не работает.** `Связь с Ozon` не имеет обработчика. Пояснение Ozon вставлено внутрь существующего диалога `Остаток FBS`, поэтому требуемого inline row expansion, выбора кандидата, отклонения и подтверждения связи нет. Это ломает полный click trace каталога.
2. **FBO-19-01 — документ начинает с выдуманного завершённого состояния.** Fixture создаёт план 10, `picked_qty=10` и завершённую упаковку 10/10 вместо контрактного плана 3, реального подбора и упаковки через текущие панели. Это скрывает, а не проверяет инвариант `0 <= packed <= picked <= plan`.
3. **FBO-19-02 — Ozon-контекст всё ещё содержит чужую и техническую семантику.** Видимы `Direct`, `Crossdock`, `Multi-cluster`, `Cargo / TGM`, `label`, `Act beta`, `auto-accept`; WB warehouse block не условно исключён для Ozon. Это нарушает operator-copy gate и исходный owner verdict.
4. **FBO-19-03 — обязательный click trace отсутствует.** Нет локального выбора destination/interval, добавления товара количеством 3 через current picker, трёх сканов, создания одного текущего WMS-короба, связывания с грузоместами, русских label states и приёмки 2/1.
5. **RET-19-01 — zero-network всё ещё не доказан и на queue mount виден прямой риск запроса.** `FfInboundQueuePage` безусловно вызывает `onRetry()` при монтировании reception даже на `return-main`. В Call 19 отсутствует request counter; следовательно прежняя фактическая поломка с backend requests не закрыта.
6. **RET-19-02 — осмотр реализован неполно.** Есть только положительные варианты `Товар совпадает` и `Без повреждений`; нет контрактных альтернатив `Товар не совпадает`, `Есть повреждения`, `Оставить отдельно`, `Зафиксировать брак`, а direct-handler negative test отсутствует.
7. **FBS-19-01 — copy/action scope не доказан.** Ozon context roots размечены частично, а связанные существующие selection/detail зоны продолжают содержать WB-текст. Нет детерминированной visible-text проверки всего Ozon root и action-intent uniqueness по каждой зоне.
8. **SET-19-01 — credentials flow не проверен на отсутствие запросов.** Локальная карточка/диалог изменены, но полный mount/click counter и negative incomplete-pair path отсутствуют; соседние screen effects остаются непроверенными.
9. **GATE-19-01 — обязательные owner gates отсутствуют.** Не добавлены и не запущены шесть armed zero-request traces, positive/negative progress tests, direct restock rejection, geometry comparison, WB observable replay и named side-by-side browser evidence.

## Что действительно прошло

- `cd frontend && npm run build` — passed при независимом повторе ведущего;
- `python3 scripts/ci/check_ozon_reuse_scope.py --self-test` — passed;
- `python3 scripts/ci/check_ozon_reuse_scope.py --base cd17496d --head WORKTREE` — passed;
- `git diff --check` — passed.

Эти проверки доказывают только сборку и отсутствие известных структурных анти-паттернов. Они не отменяют семантические находки выше.

## Узкая разрешённая коррекция

Следующий developer-call меняет только перечисленные находки, добавляет детерминированные тесты/trace и не создаёт новые product surfaces. До полного machine acceptance частичный diff не коммитится как продуктовый результат и не передаётся browser judge.
