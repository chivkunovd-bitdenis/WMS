# F3: полнота требований, отдельный тестовый контракт до исправления

Продуктовая база `45261220443cb1ffb0c2fd03522a96f23d1296ee`.
Собственный постоянный checkout `.worktrees/wms653-scope-attribution-20261006`,
ветка `codex/wms663-requirements-completeness-contract-20261006`.
Тестировщик — фактический Sol 6.1. Поле `requirements_complete` согласовано с
разработчиком priority_663 до runtime-изменений: вычисляемая полнота снимка
относительно уже существующих SKU/количеств заказа, без новой таблицы или состояния.

## Единственное уточнение прежней положительной фикстуры

Отдельный commit `a08c98f77d9f39d0ed7991bb8fd6f19f21ebef62` меняет ровно одну
строку в `OzonDocumentsAbsence.required-orders.dom.test.tsx`: полному ответу B
добавлен `requirements_complete:true`. B уже имел полный снимок, два false-флага
требований и absence_selected=false; это уточнение ранее заявленной полноты данных.
Все assertions, порядок открытия/клика/reopen, число запросов и остальные данные
сохранены. Это не разрешение править frozen ожидания. Исходный frozen contract —
`68c3bd3052e201c16b8f9a1d0fe1282cc91615c3`; ведущий получил отдельную точную дельту
для последующего reviewed owner-supersessions record. Checker/ledger не менялись.

## Новые узкие контракты

Backend: одна функция с тремя входами — полный снимок двух локальных SKU с
количествами2/1; отсутствующий второй SKU; недостающий экземпляр первого SKU.
Штатный GET возвращает все видимые required-флаги false во всех трёх случаях,
но должен выдавать requirements_complete=true только для полного варианта,
false для обоих неполных. Открытие не делает SET.

Frontend: одна параметризованная DOM-проверка false/undefined. Неполный снимок
содержит только SKU без требований, пропустив другой SKU. False или отсутствие
requirements_complete не позволяют объявить отправление не требующим документов.
Открытие не пишет, явный клик делает один POST текущего order/version4; сервер
возвращает полный выбранный результат. Новых кнопок и панелей нет.

## Фактический результат на базе452 до исправления

Backend команда из backend:
`/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q tests/test_wms663_requirements_completeness_contract.py`.
**3 FAIL**, 1.03 s: существующий GET возвращает None вместо явного bool в каждом
варианте. До этих точек реальный GET и false-флаги выполнены; environment errors нет.
Ruff нового backend-файла PASS.

Frontend команда из frontend:
`npm exec --yes --package=node@20 -- node node_modules/vitest/vitest.mjs run src/screens/v2/OzonDocumentsAbsence.incomplete-requirements.dom.test.tsx src/screens/v2/OzonDocumentsAbsence.required-orders.dom.test.tsx --no-file-parallelism`.
**2 FAIL / 1 PASS**, 2.25 s. Оба новых отказа — отсутствующий явный POST при false
и undefined. Положительный B с единственным уточнением полноты — PASS, включая
неизменные transport/checked/reopen assertions. Последующие assertions новых
негативных cases на RED ещё не достигнуты, их PASS не заявляется.

Новые два файла фиксируются отдельным canonical test commit до runtime-кода.
Другие тесты, guards, runtime, общая матрица, CI, local Chrome/Playwright не менялись
и не запускались. Разработчик получает SHA и точные команды сразу после push.
