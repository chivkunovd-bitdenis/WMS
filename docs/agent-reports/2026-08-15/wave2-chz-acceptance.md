# ORDER 033 — acceptance artifact по экрану «Честный знак» CZ-01..CZ-04

Дата: 2026-08-15 16:45 MSK.
Worktree: `/Users/deniscivkunov/Projects/WMS/.worktrees/wave2-chz-20260815`.
Ветка: `iteration/wms-wave2-chz-20260815`.
Модель: пользователь просил `gpt-5.5 high`; в текущем треде переключение модели недоступно, работа выполнена текущей моделью.

## Экран

Честный знак: карточка товара, лента расхода КМ, печать КМ и брак КМ.

## Стадия

Задним числом оформлен acceptance artifact после разработки и merge в integration. Это не новая разработка и не правка UI/бизнес-кода.

## Статус

`ACCEPTANCE_ARTIFACT_RECORDED_WITH_BROWSER_BLOCKER`.

По коду и targeted backend-проверкам CZ-01..CZ-04 выглядят закрытыми. Живой внешний Chrome-прогон ChZ из этого worktree повторить не удалось из-за инфраструктурного блокера: frontend-зависимости отсутствовали, `npm ci` упал по `ENOSPC`, а уже открытая внешняя вкладка Chrome на `127.0.0.1:5174` не имела активного Vite/API-сервера.

## Commit

Implementation до acceptance artifact: `1b4871100632e57b78e5741bfdafa8f2841d508f` (`1b48711`, `checkpoint: preserve wave2 chz follow-up`).

Предыдущий ChZ checkpoint: `240036c` (`checkpoint: preserve wave2 chz work`).

`origin/integration/wms-wave0-20260814` уже содержит `1b4871100632e57b78e5741bfdafa8f2841d508f` как merge-base; отдельно пользователь сообщил merge в integration как `06f6840`.

Artifact-only commit: commit, добавляющий этот файл; SHA фиксируется в финальном ответе Codex, потому что файл не может содержать собственный финальный SHA без изменения этого SHA.

## Тесты реальные цифры

- Backend `uv run ruff check .`: `All checks passed!`.
- Backend `uv run mypy .`: `Success: no issues found in 258 source files`.
- Backend targeted pytest с уникальной sqlite `/tmp/wms_wave2_chz_acceptance_pytest_20260815_1549.sqlite`: `8 passed in 26.16s`.
- Frontend `npm run build`: не дошёл до сборки, `sh: tsc: command not found`, потому что `node_modules` отсутствовал.
- Frontend `npm ci`: `FAILED`, причина `ENOSPC: no space left on device`.
- Frontend e2e: не запускался после `ENOSPC`, чтобы не плодить частичные зависимости и не трогать чужие worktree.

## Браузер

Способ управления: внешний Google Chrome через CDP, порт `9222`.

Факт CDP: `curl http://127.0.0.1:9222/json/version` вернул `Chrome/151.0.7922.138` и `webSocketDebuggerUrl`.

Состояние вкладок: была вкладка `http://127.0.0.1:5174/app/ff/reception`, но `lsof` не нашёл активного listener на `5174` и `18000`; live ChZ-сценарий в этой вкладке не засчитан.

Итог: `PRODUCT_BROWSER_BLOCKED`, не `PRODUCT_BROWSER_APPROVED`.

## Находки Стоп-Тормоз-Хвост

Стоп:
- Для самого ChZ-поведения по статическому коду и targeted backend-тестам стоп-находок не зафиксировано.

Тормоз:
- Worktree отстаёт от актуальных gate-файлов: `git fetch origin && git diff --stat origin/etalon -- docs/WMS_GATE.md docs/WMS_PRODUCT_AGENT.md AGENTS.md` показал 499 insertions в трёх регламентных файлах. Файлы не подтягивались, потому что задача ограничена одним artifact-only файлом.
- Frontend build/e2e и живой ChZ Chrome-прогон заблокированы нехваткой места: `df -h` показывал около `121Mi` свободно, `npm ci` упал с `ENOSPC`.

Хвост:
- В репозитории `ORDER 033` как ChZ-артефакт не найден; этот отчёт использует ORDER 033 как номер acceptance-заказа из текущего пользовательского поручения.

## Раунд

Раунд: post-merge acceptance artifact, round 1. Правок UI и бизнес-кода не было.

## Блокеры

- Нельзя честно поставить `PRODUCT_BROWSER_APPROVED`: live external Chrome-прогон ChZ не повторён.
- Нельзя честно поставить full frontend gate: `npm run build` и e2e не выполнены из-за отсутствующих зависимостей и `ENOSPC`.
- Gate-файлы в этой ветке отличаются от `origin/etalon`; для artifact-only задачи они не обновлялись.

## 6а mapping по видимым элементам CZ-01..CZ-04

| Видимый элемент / поведение | ID задачи | Где видно / чем подтверждено | Acceptance note |
|---|---:|---|---|
| Лента расхода после печати показывает полный `КМ/CIS` | CZ-01 | `HonestSignProductPage.tsx`: колонка `КМ/CIS`, вывод `row.cis_code ?? row.cis_masked`; `HonestSignLedgerPage.tsx`: вывод `row.cis_code ?? row.cis_masked` | Полный CIS отдаётся API и показывается в ленте, кроме агрегированных import-событий. |
| Лента показывает сотрудника | CZ-01 | `HonestSignProductPage.tsx`: колонка `Сотрудник`, вывод `row.actor_email`; ledger API содержит actor fields | Видимый сотрудник есть в карточке товара и ленте. |
| Лента показывает источник процесса человекочитаемо | CZ-01 | `marking_code_service.py`: labels `Каталог`, `Приёмка`, `Сортировка`, `Отгрузка`, `Упаковка/FBS-печать`; UI выводит `row.source_process_label` | Источник выведен как человекочитаемая строка. |
| Лента показывает время и связанный документ | CZ-01 | `HonestSignProductPage.tsx`: колонки `Время`, `Документ`, вывод `created_at`, `document_number` | Время и документ видны в рабочей ленте товара. |
| Повторная печать идёт как `reprint`, без нового расхода КМ | CZ-01 | `marking_code_service.py`: ветка `reprint` возвращает `is_reprint=True`; backend tests покрывают reprint/defect сценарии | Повторная печать отделена от нового расхода. |
| В карточке товара одновременно видны блоки `Коды` и `Лента` | CZ-02 | `HonestSignProductPage.tsx`: отдельные `Stack` подряд, `data-task-id="CZ-02"` и `data-task-id="CZ-02 CZ-03"` | Блоки не являются взаимоисключающими табами. |
| В блоке `Коды` видны `КМ/CIS` и статус | CZ-02 | `HonestSignProductPage.tsx`: колонки `КМ/CIS`, `Статус`, вывод `c.cis_code` и `codeStatusLabel(c.status)` | Код и статус видны на одной карточке. |
| В блоке `Лента` видны полный `КМ/CIS`, сотрудник, источник, время | CZ-02 | `HonestSignProductPage.tsx`: колонки `Время`, `КМ/CIS`, `Сотрудник`, `Источник` | Нужные поля ленты присутствуют рядом с кодами. |
| Кнопка `Вся лента товара` / переход `ff-honest-sign-product-ledger-open-full` отсутствует | CZ-03 | `rg "Вся лента товара|ff-honest-sign-product-ledger-open-full" frontend/src frontend/tests-e2e`: в UI нет, в e2e только отрицательная проверка `toHaveCount(0)` | Отдельная полная страница из карточки не открывается. |
| Пагинация внутри карточки через `Показать ещё` | CZ-03 | `HonestSignProductPage.tsx`: button `Показать ещё`, `data-task-id="CZ-03"`, `data-testid=...ledger-show-more` | Подгрузка сделана внутри карточки товара. |
| `Брак КМ` сразу фиксирует событие брака и убирает код из доступных | CZ-04 | `marking_code_service.py`: `code.status = STATUS_DEFECTIVE`, затем `EVENT_DEFECTIVE`; `test_marking_reprint_defect.py`: `code_status == STATUS_DEFECTIVE`, один defect event | Заявка на перепечать остаётся следствием, а не единственным фактом. |

## Примечания по запретам

UI и бизнес-код в рамках этой artifact-задачи не менялись. Создаётся один новый файл отчёта в `docs/agent-reports/2026-08-15/wave2-chz-acceptance.md`.
