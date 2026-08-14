---
name: wms-feature-gate
description: >-
  Обязательный WMS gate для любой задачи: BA feature cards -> Product before dev
  -> Atomic Dev -> Code Review -> Product Browser Review after dev. Используется
  при любой WMS-задаче, если пользователь прямо не объявил emergency production
  hotfix.
---

# WMS Feature Gate

## Когда включать

Включай для любой WMS-задачи, которую иначе можно ошибочно начать пилить сразу:
требование, баг, UI, backend, процесс, FBS/FBO/WB/MP, печать, deploy/release или
изменение видимого поведения. Это обязательный project-level контракт из
`AGENTS.md`, а не опциональная подсказка.

Не включай только если пользователь прямо объявил emergency production hotfix и
попросил чинить сейчас. В этом случае зафиксируй `EMERGENCY_BYPASS_USER_APPROVED`
и после стабилизации верни задачу в gate.

## Источники

1. Проверь Git-root: должен быть `/Users/deniscivkunov/Projects/WMS` или worktree
   внутри `/Users/deniscivkunov/Projects/WMS/.worktrees/`.
2. Прочитай `AGENTS.md`.
3. Прочитай `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
4. Прочитай `docs/WMS_PRODUCT_AGENT_RU.md`.
5. Прочитай `docs/MVP_DECISIONS_RU.md` и связанные текущие экраны/процессы.
6. Если есть issue/PR, проверь `### Test coverage`, но помни: это CI-слой, не
   product acceptance.

## Процедура

1. Запусти изолированный BA Agent и создай `FEATURE_CARDS_RU.md` со списком
   атомарных карточек. Без `BA_READY` разработка запрещена.
2. Запусти изолированный Product Agent до разработки по
   `docs/WMS_PRODUCT_AGENT_RU.md`. Без `PRODUCT_APPROVED_FOR_DEV` dev запрещен.
3. Запусти отдельного Atomic Dev Agent на одну утвержденную карточку.
4. После разработки запусти отдельный Code Review Agent.
5. После Code Review запусти отдельный Product Browser Review: открыть реальную
   видимую вкладку браузера, пройти клики/ввод/сканирование/успех/ошибку/пустое
   состояние и durable read-back. Playwright/API/screenshots/code reading не
   засчитываются.
6. Если product review failed или blocked, карточка не done. Rework повторяет
   цикл с BA/Product.
7. Финальный отчет всегда разделяет local, committed, pushed, deployed,
   browser-tested и blocker counts.

## Verdict

Используй статусы из `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`:

- `BA_READY`, `BA_REWORK`, `BA_BLOCKED`;
- `PRODUCT_APPROVED_FOR_DEV`, `PRODUCT_REWORK_REQUIRED`, `PRODUCT_BLOCKED`;
- `DEV_DONE`, `DEV_BLOCKED`;
- `CODE_REVIEW_PASSED`, `CODE_REVIEW_FAILED`, `CODE_REVIEW_BLOCKED`;
- `PRODUCT_BROWSER_APPROVED`, `PRODUCT_REWORK_REQUIRED`,
  `PRODUCT_BROWSER_BLOCKED`.

Положительный product/browser verdict запрещен без изолированного агента,
профессиональной WMS/логистической критики, evidence и реальной видимой вкладки
браузера после разработки.
