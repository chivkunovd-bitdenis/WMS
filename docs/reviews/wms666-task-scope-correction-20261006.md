# WMS-666: коррекция проверки границ в общей сборке

Отдельный тестировщик Sol 6.1; не автор кода WMS-666. Основа общей сборки:
`08e0d33ddb54dfa5f0712a316d879032441206dc`.
Точный test-only commit: `b1d7e39d8a812e36b47685a409267a906c85ae55`.
Ownership: только scope-тест, canonical ledger666 и этот короткий proof.
Продукт, checker652, исходные assertions запрета и соседние тесты не изменены.

## Что проверяется

Прежний тест сравнивал весь HEAD с0f1460b02 и отклонял законные задачи662/663,
миграции и stock других ветвей etalon, а также собственные browser proof666.
Теперь читается текущая история HEAD после исходного UI-контракта
`0e078418bcb7ee45fa654b0d829e5de0ec80ebb0`, а не неизменная пара исторических SHA.
Выбор task666 делается по lineage и основному номеру666 в начале subject.
Полные changed paths этих коммитов поступают в валидатор без предфильтрации.
Обычные коммиты — весь diff; merge666 — combined diff(--cc), который проверяет
новые merge-правки вместо чужого импортированного дерева. Незакоммиченные
tracked/staged/untracked пути тоже проверяются; отсутствие исходной истории
вызывает отказ. Это scope666; соседние задачи проверяют свои собственные границы.

Изначальные отрицательные assertions backend/models, migrations, inventory,
guards и чужих correctionJSON/Markdown сохранены. Добавлены только точные
собственные runner/e2e/review пути, namespace evidence/WMS-666 и два конкретных
общих proof-файла, фактически записанных merge666. Произвольные backend,
миграции, stock, guards и соседние corrections не разрешены.

## Один целевой прогон после сведения продукта

06.10.2026 15:34:23 Asia/Tbilisi, Vitest3.2.6:
`node node_modules/vitest/vitest.mjs run src/screens/v2/wms666ChangeScope.test.ts --configLoader runner --no-file-parallelism`

Результат: **1 файл / 5 тестов PASS**, длительность4.45s. Существующие два теста
сохранены; три дополнительных проверяют exact proof namespaces, реальное
развитие task-history и запрещённую правку в merge.

На отдельном временном Gitrepo законный663backend плюс666UI проходит. После
нового666commit отклоняется каждый из шести путей: уже существующий чужойbackend,
миграция, модель, inventory, guards и correction667. Незакоммиченный и staged
inventory отклоняется. Merge666 с законным импортом663backend и новой собственной
inventory-правкой отклоняет именно inventory. Это фактические Git-операции,
не подстановка готового массива для collector. Полный CI не запускался.

Первая команда запуска имела лишний frontend-префикс при cwd=frontend и упала
до Vitest с MODULE_NOT_FOUND; каталог исправлен, тесты выполнились один раз.
Доступный общий node_modules использован через игнорируемую ссылку без установки;
Chrome/Playwright не запускались.

## Каноническая коррекция и происхождение

Фактический checker общего08e0 содержит последовательный exact fixture-путь
только для предопределённых полных blob-пар517/663. Для generic corrections666
он по-прежнему запрещает пересечение файлов одного исходного контракта
(`corrected_by_contract`, строки507–509). Поэтому новая запись поверх прежней
для того же scope-файла была бы честно отвергнута; checker не изменялся.

Две прежние canonical scope references заменены cumulative ссылками на новый
отдельный test-onlySHA. Независимая DOM correction a29e3b33 сохранена без изменений.
Новая scope correction является надмножеством старой: источник08e0 содержит
принимаемый5e10scope; текущая дельта сохранила прежнюю JSON-границу и все её
отрицательные assertions, затем исправила attribution и добавила negative controls.
Исходные contract/review SHA остаются предками HEAD. Старые записи полностью
сохранены ниже; история original ledger тоже сохраняется в Git.

Новый review имеет **PENDING**, не PASS. Локальные тесты не заменяют отдельное
Astra high ревью. Проверка документов относительно08e0 прошла, но её диапазон
не включает старые contracts; полный etalon-диапазон и protection должны отказать
до реального PASS новой коррекции. После независимого заключения ведущего
заменить PENDING реальным verdict и сохранить SHA/evidence ревью, затем
проверить canonical ledger без изменения checker.

### Предыдущие записи scope-коррекции

```json
[
  {
    "contract_commit": "0e078418bcb7ee45fa654b0d829e5de0ec80ebb0",
    "correction_commit": "5e10a98683b2ae91ce90d2e9078cc3ce86da23da",
    "files": [
      "frontend/src/screens/v2/wms666ChangeScope.test.ts"
    ],
    "review": {
      "model": "gpt-6-astra",
      "effort": "high",
      "verdict": "PASS",
      "session_id": "01a10fde-71bf-7242-9dda-4a1ad3572219",
      "checker_commit": "8d6cdd80c7e478bda46371d79911a6e3c902d5c9",
      "evidence": "Exact WMS-666 JSON allowance; adjacent task JSON and Markdown rejected; original rejection expectations intact; corrections disjoint within original contract. Proposed ledger accepted in memory with no contract-change errors."
    }
  },
  {
    "contract_commit": "071a05daca43a9c29a4152c6666601a9d9a5e5cd",
    "correction_commit": "5e10a98683b2ae91ce90d2e9078cc3ce86da23da",
    "files": [
      "frontend/src/screens/v2/wms666ChangeScope.test.ts"
    ],
    "review": {
      "model": "gpt-6-astra",
      "effort": "high",
      "verdict": "PASS",
      "session_id": "01a10fde-71bf-7242-9dda-4a1ad3572219",
      "checker_commit": "8d6cdd80c7e478bda46371d79911a6e3c902d5c9",
      "evidence": "Only scope-test comment changed after this contract; scan fixture byte-identical to 071a05da. Strict subset and exact changed paths confirmed."
    }
  }
]
```
