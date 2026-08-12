# TL-F010 — Основные FF/seller экраны обрезают действия и данные справа даже на 1920 px

## Паспорт

- Finding ID: `TL-F010`
- Title: operator cannot see the right side of forms, action groups and tables at a verified 1920 CSS-pixel desktop viewport
- Class: `BUG`
- Severity: P2
- Area / scenario ID: shared FF/seller desktop layout
- First reviewer / independent verifier: orchestrator execution / teamlead visual adjudication
- Environment and SHA: staging; component SHA attribution blocked
- Role / tenant / seller test IDs: synthetic administrator and seller
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: supported review viewport and visible operator controls.
- Короткое ожидаемое поведение: all primary actions and table columns fit or have an obvious local scrolling mechanism.

## Фактическое поведение и воспроизведение

- Steps: open each route, wait two seconds, capture at `innerWidth=1920`, DPR1.
- User-visible: subtitles, action groups, cards and columns continue past the right PNG edge on Dashboard, MP, FBS, Reception, Sorting, Packaging, Sellers, Catalog, Honest Sign, Settings and seller routes. Creation dialogs are cut at right/bottom.
- Data effect: no direct corruption; operators can miss or be unable to reach controls and context.
- Repeatability: across stable FF/seller routes; early transition frames excluded.

## Доказательства

- screenshots: exact files and SHA-256 for all 12 stable FF plus four stable seller routes in `ui-evidence/index.md`.
- reload proof: MP list and FBS reload retain the wide presentation.
- code path: layout cause not asserted; this finding is visual/runtime only.
- tests: current desktop screenshots do not fail on horizontal document overflow.

## Ущерб и граница

- Кто страдает: desktop FF administrators and seller operators.
- Результат: hidden controls/data and avoidable horizontal navigation.
- Workaround: browser zoom-out or horizontal document scroll, when available; harms readability.
- Почему дефект: supported desktop viewport does not present the full existing workflow.
- Не входит: redesign, mobile responsiveness, or transitional dark frames.

## Критерий закрытия

- Given: CSS 1920×1080/DPR1 and 1280×720
- When: every listed route and create dialog is opened
- Then: primary actions/context are visible, dialogs fit, and any wide table has explicit local scrolling
- And: document width does not exceed viewport unless an intentional, visible scroller owns the overflow

## Вердикт оркестратора

- Accepted: accepted after orchestrator rechecked original stable images
- Queue status: accepted P2
