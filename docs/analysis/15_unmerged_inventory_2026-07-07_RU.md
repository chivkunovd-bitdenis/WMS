# Инвентаризация незалитого перед релизом печати

Дата: 2026-07-07

Рабочий checkout с историей: `/Users/deniscivkunov/Desktop/WMS `.
Папка `/Users/deniscivkunov/Desktop/WMS` без пробела не является git-репозиторием.

## Продовая база

Текущая prod-base по GitHub Actions и `origin/main`:

- `origin/main`: `5b4bd9c fix(inbound): align receiving table header`.
- Последний `Deploy Production`: success, run `28791427168`, `2026-07-06 12:27:00Z`, `headSha=5b4bd9c`.
- Значит при инвентаризации считаем продом `origin/main@5b4bd9c`.

## Что уже на проде из последних фичей

| PR | Merge SHA | Дата merge | Статус deploy | Что закрывает |
|---|---|---:|---|---|
| #70 | `aa76d57` | 2026-07-05 | в `5b4bd9c` | базовая раздельная печать ЧЗ/ШК, настройка tenant, scanner release, первичная чистка MP упаковки |
| #71 | `c4b7384` | 2026-07-05 | в `5b4bd9c` | удаление незапрошенной пачечной/chunk-печати |
| #72 | `7328aa1` | 2026-07-05 | первый deploy упал, позже вошло в успешные deploy 2026-07-06 | box XLSX import, CZ shared basket/catalog write-off |
| #73 | `f62b590` | 2026-07-06 | success run `28783305890` и позже | reopen receiving, blur qty save, qty column in TZ sheet |
| #75 | `2eec67c` | 2026-07-06 | success run `28786669087` и позже | inbound qty no longer resets to 0 on blur |
| #76 | `7a66b2b` | 2026-07-06 | success run `28790080579` и позже | растянуть receiving table |
| #77 | `5b4bd9c` | 2026-07-06 | success run `28791427168` | выравнивание header/body receiving table |

Вывод: основная пачка 2026-07-05/2026-07-06 уже в prod-base. Незалитое сейчас не равно "надо вливать старые ветки целиком".

## Почему текущую локальную ветку нельзя вливать целиком

Текущая локальная ветка в исходном checkout:

- `hotfix/inbound-qty-blur-v2`
- `HEAD=4d21bda chore: retrigger CI after PR test coverage body fix`
- `ahead 2, behind 3` относительно `origin/main`

`git cherry -v origin/main hotfix/inbound-qty-blur-v2`:

- `1bdfec7 fix(inbound): stop qty save resetting to 0 on blur/pencil click` уже patch-equivalent с merged PR #75 (`2eec67c`).
- `4d21bda chore: retrigger CI after PR test coverage body fix` не содержит runtime-изменений.

При этом ветка не содержит последние `7a66b2b` и `5b4bd9c`, которые уже на проде. Поэтому broad merge этой ветки создаёт риск отката/конфликтов без бизнес-выгоды.

## Отобрано в новую ветку

Новая clean-ветка: `hotfix/cz-print-regression-2026-07-07`, база `origin/main@5b4bd9c`.

Берём только связанный print/CZ набор:

| Блок | Файлы | Зачем | Риск |
|---|---|---|---|
| Раздельная печать не должна склеиваться | `frontend/src/utils/separateMarkingPrint.ts`, `frontend/src/components/MarkingPrintDialog.tsx` | при открытии диалога перечитать `/auth/me`, сохранить tenant flag локально, не показывать общий конструктор пока профиль проверяется | низкий: меняет только режим товаров с ЧЗ и tenant flag |
| Scoped размеры ЧЗ/ШК | `frontend/src/utils/labelSize.ts`, `frontend/src/utils/labelSize.test.ts` | `cz` и `label` больше не наследуют старый общий `70x120`; default `58x40` для раздельной печати | средний: меняет первое открытие размера для пользователей без scoped-настройки |
| MP упаковка без лишнего ТЗ в строке | `frontend/src/screens/ff/FfPackagingPage.tsx` | убрать длинную инструкцию из таблицы упаковки; не ломать строку документа | низкий: UI cleanup, e2e проверяет отсутствие текста |
| Reprint внутри диалога | `frontend/src/components/MarkingPrintDialog.tsx` | если КМ уже печатались, кнопка ЧЗ ведёт в существующий pick-list перепечатки, а ШК ВБ остаётся отдельным | средний: связано с backend правилом `already_printed_use_reprint` |
| PDF artifact safety | `backend/app/services/marking_code_service.py`, `backend/app/api/marking_codes.py` | multi-label PDF page не отдаётся как artifact одной этикетки; для таких КМ фронт печатает generated label нужного размера | средний: меняет `has_label_artifact` для старых multi-label PDF; это ожидаемый rollback на безопасную печать |
| Тесты | `backend/tests/test_marking_pdf_label_artifact.py`, `frontend/tests-e2e/ff-mp-packaging-print.spec.ts`, `frontend/tests-e2e/ff-separate-marking-print.spec.ts` | закрепить regressions: split print, default 58x40, no glued tape, no multi-label artifact reuse | низкий |

Дополнительная правка при подготовке ветки:

- `is_printable_label_artifact` теперь не падает на битом PDF и кэширует распознанные CIS для одного PDF bytes. Это нужно, чтобы safety-check в списках кодов не превратился в лишний CPU/500.

## Не берём в релиз

| Что | Решение | Причина |
|---|---|---|
| `TASKLOG.md` из исходного checkout | не брать | только локальная отметка по уже merged PR #73 |
| `frontend/src/screens/ff/FfInboundRequestView.tsx` и `frontend/tests-e2e/inbound-receiving-v2.spec.ts` | не брать | `git diff origin/main` пустой: это уже prod-base |
| `docs/analysis/13_mp_unload_pick_without_box_tasks_RU.md` | не брать | отдельный backlog по MP pick-without-box, не runtime fix печати |
| `docs/analysis/14_cz_label_print_prod_rollout_RU.md` | не брать | черновой rollout-план заменён этой инвентаризацией |
| `frontend/scripts/render-cz-*.mts`, `scripts/render_cz_preview_from_pdf.py` | не брать | QA/preview tooling, не нужно для runtime |
| `output/` | не брать | generated PDF/PNG evidence |
| `mobile/` | не брать | вложенный git-проект, Android app и `wms-tsd-release.jks`; отдельный security/release процесс |
| старые worktree `.cursor/wt/*` | не брать | исторические task-ветки, многие prunable |

## Старые незалитые ветки

| Ветка | Статус | Решение |
|---|---|---|
| `hotfix/inbound-qty-blur-v2` | функциональный commit уже merged в #75, сверху retrigger-only | не merge |
| `hotfix/inbound-table-header-alignment` | функциональный commit уже merged в #77, сверху retrigger-only | не merge |
| `feat/composer-tasks` | commits patch-equivalent с #73/#75 | не merge |
| `task/PACK-01` | patch-equivalent с текущей базой | не merge |
| `task/PACK-02`, `task/PACK-03` | формально не patch-equivalent, но целевые UI (`print-all`, verify-pair) уже отсутствуют в `origin/main` | не merge |
| `origin/feat/product-barcode-print` | patch-equivalent с текущей базой | не merge |
| `hotfix/deploy-wb-sync-nonfatal` | patch-equivalent с merged PR #58 | не merge |
| `chore/railway-toml-fix` | отдельная Railway/staging конфигурация | не включать в print hotfix |
| `chore/release-via-pr-only-rules` | process/docs guard | отдельный infra/process PR, не runtime |
| `chore/visual-audit-harness` | большой harness, seed и review-доки | отдельный tooling PR после ревью |
| `task/IN-BE-03`, `task/OUT-FE-02` | старые task docs/UI branches, далеко behind prod | не включать без нового product review |

## Порядок заливки

1. PR из `hotfix/cz-print-regression-2026-07-07` в `main`.
2. В PR явно указать, что base = `5b4bd9c`, а broad merge старой `hotfix/inbound-qty-blur-v2` запрещён.
3. Gate до merge:
   - backend: `ruff` на изменённые backend-файлы;
   - backend: `pytest backend/tests/test_marking_pdf_label_artifact.py`;
   - frontend: `npx tsc --noEmit`;
   - frontend: `npm run test:unit -- --run src/utils/labelSize.test.ts src/utils/markingPrintPresets.test.ts`;
   - frontend: targeted Playwright `tests-e2e/ff-mp-packaging-print.spec.ts`.
4. После deploy: ручная проверка tenant с `separate_marking_print_enabled=true`: открыть MP упаковку ЧЗ-товара и убедиться, что нет общей склеенной ленты, есть отдельные блоки ЧЗ/ШК ВБ.

## Rollback

- Если проблема только в split-mode: временно выключить tenant flag `separate_marking_print_enabled`.
- Если проблема только в PDF artifact: rollback backend-части не обязателен срочно, безопасный fallback печатает generated CZ label вместо ужатой multi-label PDF page.
- Если ломается открытие диалога печати вообще: revert PR целиком.
