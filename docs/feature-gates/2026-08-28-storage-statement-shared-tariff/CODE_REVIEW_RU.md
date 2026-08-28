# Финальный Code Review A-1 — ведомость хранения на общей матрице

## Область проверки

Проверен итоговый A-1 diff против Feature Card, Product Before Dev и ломающего
тест-плана. Основной фокус повторного review: единая seller/day аллокация между
складами, неизменность результата при `warehouse_id`, сохранность fixed ledger,
tenant/seller/role scope и устранение промежуточной регрессии проверки
непредставимых ledger-значений. Production-код и тесты ревьюером не менялись;
обновлён только этот review-артефакт.

## Закрытые находки

### A1-CR-001 — закрыта

Дневной расчёт сохраняет точные доли копейки, затем округляет общий seller/day
target через `ROUND_HALF_UP` и распределяет целые копейки методом наибольших
остатков. Публичные суммы строк имеют денежный формат с двумя знаками. Для двух
строк по `0.0049` литро-дня при ставке 100 копеек сумма строк, ведомость, seller
report и invoice preview равны 1 копейке.

### A1-CR-002 — закрыта

После сохранения common/seller версии выбираются по точным tenant, seller scope,
service, unit, enabled, rate и effective start. Перекрёстная история дат A/B не
может вернуть старую строку с совпавшей ставкой или более поздней датой.

### A1-CR-003 — закрыта

Все warehouse statements одного tenant/seller/period участвуют в общей
seller/day аллокации. Стабильный tie-break использует строковое представление
measurement UUID. Поэтому две складские ведомости по `0.0049` литро-дня дают
вместе ровно 1 копейку — ту же сумму, которую уже рассчитывают seller report и
invoice. Этот же batch применяется в list preview, ответе массового reprice и
при фиксации ledger.

### A1-CR-004 — закрыта

`list_statements` сначала загружает все операционные склады своего tenant, затем
по их полному множеству выбирает statements и measurements для allocation scope.
Параметр `warehouse_id` применяется только к списку складов и ведомостей,
возвращаемых клиенту; он больше не обрезает pricing batch.

Регрессионный тест создаёт два склада по `0.0049` литро-дня, получает
нефильтрованный ответ и каждый склад отдельно. Он доказывает неизменность
`total_amount`, measurement `amount` и `rate_snapshot`, а также равенство
нефильтрованной суммы, seller report и invoice одной копейке.

## Проверено без находок

- Все запросы allocation scope ограничены `tenant_id` текущего пользователя и
  только операционными складами этого tenant. Чужой или неоперационный
  `warehouse_id` не расширяет scope и даёт пустую видимую выборку.
- Для `fulfillment_seller` statements и measurements дополнительно ограничены
  его `seller_id`; dependency запрещает доступ несвязанному seller. Admin видит
  tenant целиком, staff должен иметь inventory permission. Создание тарифа и
  фиксация ведомости остаются admin-only.
- Seller override имеет приоритет над common V2 rate. Ставки другого tenant или
  seller не участвуют; legacy warehouse rate 99 не используется и новая legacy
  строка не записывается.
- Fixed statement читается только из immutable ledger snapshot. Общая
  многоскладская аллокация определяет снимок при фиксации, но не переписывает уже
  опубликованные peer ledger rows.
- Промежуточная seam-регрессия устранена: односкладская фиксация снова проходит
  через `_measurement_pricing`, поэтому проверки quantity/rate/amount overflow
  сохраняют атомарный rollback. Batch raw/allocation включается только при
  нескольких priced peer scopes.
- Reprice охватывает все затронутые draft statements tenant и не изменяет fixed
  rows. Выбор новой common/seller пары после сохранения точный по scope/rate/date.
- Московская дата V2 корректно восстанавливается из naive SQLite UTC datetime.
- UI сохранил прежнюю компоновку: revision передаётся вместо ценового
  `warehouse_id`, склад показан read-only как «Все операционные склады».
  Запрещённые `warehouse-map/`, `sorting-objects/` и `ui-kit/` не затронуты.
- В diff не обнаружено несвязанных production-изменений A-1; `git diff --check`
  по A-1 файлам проходит.

## Выполненные проверки

- Scoped Ruff production и нового matrix test — pass.
- Scoped mypy трёх production-файлов — pass.
- Точный набор CR004 + CR003 + tenant/operational scope + seller override —
  **4 passed in 5.05s**.
- Три параметризации атомарного ledger overflow — **3 passed in 6.35s**.
- Финальный полный A-1 backend набор
  `test_storage_statement_service.py`, `test_storage_tariff_api.py`,
  `test_storage_statement_matrix.py` — **45 passed in 43.28s**.
- Независимый финальный tester clean run того же набора — **45 passed in
  68.25s**, итог тестового слоя — `TESTS_GREEN`.

## Неизвестное и документарный follow-up

- Полные project-wide backend/frontend gates этим изолированным review не
  запускались.
- Отдельного browser acceptance в этом review не было; его не заменяют API и
  unit/integration tests.
- Нагрузочный профиль tenant-wide seller/period batch на больших объёмах не
  измерялся и остаётся указанным в тест-плане performance risk.
- Точный CR004 integration test работает под admin. Seller isolation проверена
  чтением одинаковых seller-фильтров в statement и measurement queries и общей
  access dependency; отдельной seller-role вариации именно дробного CR004 теста
  нет.

## Вердикт

```yaml
feature_id: A-1
review_agent: /root/a1_review
isolated_agent: yes
production_or_tests_modified: no
resolved_findings:
  - A1-CR-001
  - A1-CR-002
  - A1-CR-003
  - A1-CR-004
open_findings: []
verdict: CODE_REVIEW_PASSED
next_status: PRODUCT_BROWSER_REVIEW
```

**Итог: `CODE_REVIEW_PASSED`.** Финансовая сумма теперь сохраняет seller/day
контракт между складами и не меняется от фильтра страницы; fixed ledger,
tenant/seller scope и атомарность фиксации не регрессировали. Этот verdict
закрывает code-review слой A-1, но не подменяет обновление tester verdict и живую
продуктовую проверку в браузере.
