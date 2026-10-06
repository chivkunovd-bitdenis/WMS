# Третий конкретный дефект ревью: один DOM-контракт до исправления

База продукта `d4d1c658839d1cdbb8b9e50509f046a30bf5ffa3`.
Постоянный checkout `.worktrees/wms653-scope-attribution-20261006`, ветка
`codex/wms663-required-order-checkbox-contract-20261006`.
Отдельный тестировщик — фактический Sol 6.1. Runtime и прежние тесты не изменены.

Новый файл `OzonDocumentsAbsence.required-orders.dom.test.tsx` содержит ровно один
тест реального React-компонента общей галки в DOM. Current orderIds — A и B.
Полный ответ A содержит реальный экземпляр с требованием ГТД; полный ответ B —
реальный экземпляр, gtd_required=rnpt_required=false и absence_selected=false.
Это известное отсутствие требований у B, не пустой или неизвестный ответ Ozon.

Открытие делает только GET. Явный клик должен отправить один POST только A с
expected_version4. Ответ принятого A сохраняет выбор. Общая галка должна быть
checked без indeterminate, B не получает absence POST. Новое открытие подтверждает
выбор чтением и не добавляет записи. Новых buttons/panels тест не требует.

Команда из frontend:
`npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/OzonDocumentsAbsence.required-orders.dom.test.tsx --no-file-parallelism`.

Фактический **RED: 1 FAIL**, 1.31 s, целевая точка — лишний POST B с
expected_version7. До него исходное открытие без writes и явная отправка A
выполнены. Последующие checked/reopen assertions на RED ещё не достигнуты;
их PASS не заявляется. Collection/environment failures нет.

Отдельно read-only изучена применимость охраны старых UI-контрактов. Кроме
scope666, check_task_documents фиксирует исходный 662 C19 в
`2006171f0feae5513f887b471125ecae1a96c2ae` и 663 C16 в
`ae2ebd3d17f4e7364b1b52de4126b8f70937652b`. Старый 663 ledger разрешает только
точные fixture blob transforms, которые не описывают новый owner override C16.
Текущий 662 ledger покрывает только backend c466, не C19. Эти пути отсутствуют
в guards/MANIFEST. Ведущему сообщена необходимость точного owner-overridden
reviewed record; checker, ledger, guards и исключения здесь не менялись.

Новый тест фиксируется отдельным canonical commit «WMS-663: контракт тестов»
до исправления UI. Старые два backend регрессионных сценария уже переданы
разработчику отдельно. Полная матрица, CI, Chrome/Playwright и runtime не запускались.
