# Параллельный реестр задач ЧЗ (вход для агентного режима)

> **Один файл = весь backlog для параллельной разработки 5 агентами.**
> Детали постановок (если нужно глубже): `CHESTNY_ZNAK_UX_FIXES_RU.md`, `docs/MASTER_BACKLOG_RU.md`.

---

## КОНТРАКТ ДЛЯ ОРКЕСТРАТОРА (читать обязательно)

1. **Не запускать одновременно две задачи, у которых пересекается список `files`.** Файл — единица блокировки. Иначе merge-конфликт / потеря правок.
2. **Соблюдать `depends_on`** — задача берётся в работу только когда все её зависимости в статусе `done`.
3. **`CZ-000` (коммит) — глобальный барьер.** Все задачи зависят от него. Пока не `done` — агенты не стартуют.
4. Внутри одной `lane` задачи идут **последовательно** (общий файл). Разные `lane` — параллельно.
5. Каждая задача: минимальный diff, зелёная сборка/тест, строка в `TASKLOG.md`, отдельный коммит.
6. Слово **` done`** в колонке **`id`** — только после `gate` (verifier PASS), не после builder.

**Параллельность:** 8 независимых дорожек + общие. На старте (после CZ-000) сразу доступно ≥7 задач из разных файлов → 5 агентов загружены без коллизий.

**Решения (зафиксированы):**
- Печать не-ЧЗ товара: **конструктора нет, только поле количества ШК ВБ**.
- Множитель «× кол-во в упаковке» для ШК ВБ: **и в упаковке, и в каталоге**.

---

## CZ-000 — БАРЬЕР: зафиксировать текущее done

- **files:** `—` (git-операция)
- **depends_on:** `—`
- **do:** Закоммитить/застешить незакоммиченный MP-диффф на `hotfix/alembic-marking-pools`; создать ветку `feat/cz-ux-fixes`; от неё агенты создают worktree-ветки.
- **gate:** `git status` чистый, агенты стартуют от чистой базы.
- **closed:** 2026-06-28 — MP slice `304abf2` on `hotfix/alembic-marking-pools`, branch `feat/cz-ux-fixes` created.

---

## LANE-PACK — экран упаковки (`frontend/src/screens/ff/FfPackagingPage.tsx`)

> Один файл, строго последовательно. Самая длинная дорожка — отдать сильному агенту.

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| PACK-01 | CZ-000 | Удалить скан-печать | Убрать поле «Сканируйте товар» (`marking-scan-print-field`), `submitScanPrint`, состояния `scan*` | нет элемента скан-печати |
| PACK-02 | PACK-01 | Удалить «Печать всех ЧЗ» | Убрать кнопку `ff-packaging-print-all-marking`, диалог `marking-print-all-dialog`, `confirmPrintAll`/`loadPrintAllPreview`/состояния `printAll*`; удалить `tests-e2e/ff-marking-print-all.spec.ts` | нет кнопки/диалога |
| PACK-03 | PACK-01 | Удалить «Сверку пары ЧЗ» | Убрать панель `marking-verify-pair-panel`, `submitPairVerify`, состояния `pair*`, при ненужности `hasPrintedMarkingLines`; удалить `tests-e2e/ff-marking-verify-pair.spec.ts` | нет панели сверки |
| PACK-04 | PACK-02, PACK-03 | Зачистка | Убрать осиротевшие импорты/переменные (`hasHonestSignLines` и пр.), `tsc`+eslint; проверить построчную печать ЧЗ | build+lint green |
| PACK-05 | PACK-04 | «Брак»: выбор кода + причина | Диалог выбора конкретного КМ + поле причины + подтверждение (вместо `codes[0]`); свериться: принимает ли `defect` API причину | бракуется выбранный код |
| PACK-06 | PACK-05 | «Брак»: обновление | После `defect` перезапрос задания + `onUpdated` | счётчики обновляются |
| PACK-07 | PACK-04 | Гард завершения | Предупреждение/блок при `requires_honest_sign` строках без КМ; свериться с серверной валидацией | нельзя завершить с неполной маркировкой |
| PACK-08 | PACK-04 | Прогресс «X/Y» в колонке ЧЗ | «напечатано X / нужно Y» + остаток в пуле, подсветка неполных | прогресс виден в строке |
| PACK-09 | PACK-05, PACK-06, PACK-07, PACK-08 | Действия в меню «…» | Повтор/Брак убрать в overflow-меню | ≤2–3 видимых кнопки |

---

## LANE-PRINT — окно/конструктор печати

> **files (вся дорожка блокирует):** `MarkingPrintDialog.tsx`, `markingPrintPresets.ts`, `ProductBarcodePrintDialog.tsx`, `productBarcodePrint.ts`, `FfProductLineCells.tsx`, `printTemplate.ts`, backend `models/print_template.py`, `services/print_template_service.py`, `api/marking_codes.py` (print-templates).

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| PRINT-01 | CZ-000 | Не-ЧЗ: убрать конструктор | Для не-ЧЗ товара показывать только поле количества ШК ВБ (свернуть не-ЧЗ ветку `MarkingPrintDialog` до количества; пресеты/билдер не показывать) | не-ЧЗ → только количество |
| PRINT-02 | PRINT-01 | Убрать заглушку «Запросить у селлера» | Удалить кнопку `marking-print-request-seller` | нет заглушки |
| PRINT-03 | PRINT-01 | Переименовать блок `label` → «ШК ВБ» | Лейблы в билдере/пресетах (без смены `data-testid`) | в UI «ШК ВБ» |
| PRINT-04 | PRINT-01 | Множитель в каталоге | «× кол-во в упаковке» для ШК ВБ применить и в каталожной печати (`ProductBarcodePrintDialog`/`productBarcodePrint`) | qty 3 при 5 шт → 15 в обоих контекстах |
| PRINT-05 | PRINT-02, PRINT-03, PRINT-04 | Раскладка на учётке пользователя | backend: `user_id` в `print_templates` + миграция, приоритет в `resolve` на раскладку юзера, авто-сохранение последней на печати без имени; frontend подхватывает | Вася и Петя — каждый своя раскладка |

---

## LANE-LEDGER — лента расхода (`frontend/src/screens/shared/HonestSignLedgerPage.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| LEDGER-01 | CZ-000 | Название пула вместо UUID | В баннере «Фильтр по пулу» показывать имя пула | имя пула в баннере |
| LEDGER-02 | LEDGER-01 | Серверный поиск по маске КМ | Передавать маску на сервер; убрать клиентскую фильтрацию; свериться с API | поиск по всей базе |
| LEDGER-03 | LEDGER-01 | Фильтр по диапазону дат | Поля «с/по», передать на сервер | фильтр по периоду |
| LEDGER-04 | LEDGER-03 | Экспорт по фильтрам | Серверный экспорт текущей выборки | выгрузка файла |
| LEDGER-05 | LEDGER-02 | Единая модель фильтров | Убрать двусмысленность кнопки «Применить» (дебаунс/единый триггер) | предсказуемые фильтры |
| LEDGER-06 | LEDGER-01 | Локализация типов событий | Использовать общий словарь (`markingStatus.ts`); зависит от SHARED-01 | события по-русски |

---

## LANE-IMPORT — импорт кодов (`frontend/src/screens/shared/MarkingImportDialog.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| IMPORT-01 | CZ-000 | Не терять данные при добавлении файла | Мержить группы по `gtin`, сохраняя `title`/`productIds` | правки сохраняются |
| IMPORT-02 | IMPORT-01 | Поиск товаров per-group | Своя строка поиска на каждую GTIN-группу | поиск не влияет на др. группы |
| IMPORT-03 | IMPORT-01 | Убрать тихий кэп 8 | «Показать ещё»/подпись «первые 8 из N» | усечение видно/обходится |
| IMPORT-04 | IMPORT-01 | Удаление добавленного файла | `onDelete` на чипах файлов + пересбор превью | файл можно убрать |
| IMPORT-05 | IMPORT-01 | Подсветка группы без названия | Подсветить пустые `title`, скролл к первой | видно где пусто |

---

## LANE-POOLS — список пулов (`frontend/src/screens/shared/HonestSignScreen.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| POOLS-01 | CZ-000 | Селлер через поиск | Заменить ряд кнопок селлеров на Autocomplete/Select | удобно при 30+ |
| POOLS-02 | POOLS-01 | KPI: честная кликабельность | Сделать осмысленно кликабельными или оформить иначе | вид = поведение |
| POOLS-03 | POOLS-01 | Tooltip на disabled «Загрузить коды» | Подсказка «выберите селлера» | понятно почему disabled |
| POOLS-04 | POOLS-01 | Убрать дубль дашборд+таблица | Переключатель или карточки=проблемные | нет двойного показа |
| POOLS-05 | POOLS-01 | Единый формат прогноза | Один формат в таблице и карточках | одинаково |
| POOLS-06 | POOLS-01 | Один CTA на привязку | Убрать дубль чип+кнопка | одно действие |

---

## LANE-POOLCARD — карточка пула (`frontend/src/screens/shared/HonestSignPoolPage.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| POOLCARD-01 | SHARED-01 | Локализация статусов кодов | Использовать общий словарь в фильтре/чипах | статусы по-русски |
| POOLCARD-02 | CZ-000 | Экспорт всех кодов | Серверный экспорт либо честная подпись «N из M» | полная выгрузка/подпись |
| POOLCARD-03 | CZ-000 | Таб «Лента» → превью + ссылка | Короткое превью + ссылка на полную ленту пула | нет дублирующей ленты |

---

## LANE-REPRINTS — перепечатки (`frontend/src/screens/ff/FfHonestSignReprintsPage.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| REPRINTS-01 | CZ-000 | Объяснить «Подтвердить/Заменить» | Подписи/тултипы с последствиями | понятны последствия |
| REPRINTS-02 | REPRINTS-01 | Причина отклонения | Поле причины при reject (вместо хардкода) | реальная причина |
| REPRINTS-03 | REPRINTS-01 | Контекст для решения | Ссылки на задание/пул/историю кода | контекст доступен |

---

## LANE-PENDING — осталось промаркировать (`frontend/src/screens/ff/FfPendingMarkingPage.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| PENDING-01 | PRINT-01 | Массовая печать по списку | Чекбоксы строк + печать выбранных, **каждая лента по своему товару** | печать по выбранным |

---

## LANE-SHARED — общий словарь (`frontend/src/utils/markingStatus.ts` [новый], `MarkingProductCodesDialog.tsx`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| SHARED-01 | CZ-000 | Словарь статусов/событий | Создать `markingStatus.ts` (`codeStatusLabel`, `ledgerEventLabel` с фолбэком); перевести `MarkingProductCodesDialog` на него (убрать локальный `STATUS_LABEL`) | словарь готов, диалог использует |

---

## LANE-BACKEND — депрекейт (`backend/app/api/marking_codes.py`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|----|
| BACKEND-01 | PACK-01, PACK-02, PACK-03 | Deprecate scan-print/print-all/verify-pair | Пометить эндпоинты deprecated (фронт их уже не зовёт) + тикет на удаление | deprecated проставлен |

---

## CROSS — задачи на 2 файла (оркестратор блокирует ОБА указанных файла)

> Эти задачи трогают файлы из разных дорожек → запускать, когда обе зависимости `done` и оба файла свободны.

| id | files | depends_on | title | do | gate |
|----|-------|-----------|-------|----|----|
| CROSS-01 | FfPackagingPage.tsx, MarkingPrintDialog.tsx | PACK-05, PRINT-05 | «Повтор»: перепечатка одного КМ | Выбор конкретного кода для повторной печати (reprint-ветка диалога + проброс из строки) | можно перепечатать один код |
| CROSS-02 | FfPendingMarkingPage.tsx, FfPackagingPage.tsx | PACK-09, PENDING-01 | Контракт `total` vs `rows` | Свериться с `/pending-marking`; привести бейдж и список к единому контракту | бейдж = число строк |
| CROSS-03 | HonestSignScreen.tsx, HonestSignLedgerPage.tsx | POOLS-06, LEDGER-05 | Селлер-селект в ленте | Тот же Autocomplete селлера на странице ленты | единый выбор селлера |
| CROSS-04 | HonestSignScreen.tsx, MarkingImportDialog.tsx | POOLS-06, IMPORT-05 | «Догрузить» с контекстом пула | Передавать gtin/title/товары пула в импорт для предзаполнения | импорт с контекстом |

---

## FINAL — одиночные «хвосты» (после всех соответствующих дорожек)

| id | files | depends_on | title | gate |
|----|-------|-----------|-------|----|
| FINAL-01 | (много, single-thread) | все LANE-* | Единый термин (КМ/ЧЗ) по лейблам | нет смеси терминов |
| FINAL-02 | (анализ → подзадачи) | LEDGER-*, POOLCARD-03 | Аудит дублей поверхностей (две ленты, два списка кодов, два импорта) | план/правки |
| FINAL-03 | docs | все LANE-* | Перенести `CHESTNY_ZNAK_UX_FIXES_RU.md` в `docs/`, закрыть T-A7 как дубль, свериться со старым `CHESTNY_ZNAK_FIX_TASKS_RU.md` | доки согласованы |

---

## Карта блокировок (для проверки параллельности)

| Файл | Чья дорожка |
|------|-------------|
| FfPackagingPage.tsx | LANE-PACK (+ CROSS-01, CROSS-02) |
| MarkingPrintDialog.tsx, markingPrintPresets.ts, ProductBarcodePrintDialog.tsx, productBarcodePrint.ts, FfProductLineCells.tsx, printTemplate.ts, backend print_template* | LANE-PRINT (+ CROSS-01) |
| HonestSignLedgerPage.tsx | LANE-LEDGER (+ CROSS-03) |
| MarkingImportDialog.tsx | LANE-IMPORT (+ CROSS-04) |
| HonestSignScreen.tsx | LANE-POOLS (+ CROSS-03, CROSS-04) |
| HonestSignPoolPage.tsx | LANE-POOLCARD |
| FfHonestSignReprintsPage.tsx | LANE-REPRINTS |
| FfPendingMarkingPage.tsx | LANE-PENDING (+ CROSS-02) |
| markingStatus.ts (new), MarkingProductCodesDialog.tsx | LANE-SHARED |
| backend api/marking_codes.py | LANE-BACKEND |

> Пока CROSS-задача в работе — её два файла заняты, соответствующие дорожки ждут. Поэтому CROSS поставлены в конец (после основных задач их дорожек).
