# Temporal — durable workflow execution и resume

## 1–2. Ссылка и доказательность

[Workflow Execution overview](https://docs.temporal.io/workflow-execution), official documentation, проверено 2026-08-24. E1 для документируемой platform semantics.

## 3–5. Задача и happy path

Workflow Execution — server-side durable instance с Workflow ID/Run ID и event history. Worker исполняет Workflow Task, возвращает commands; service сохраняет события и планирует следующие tasks. При нормальном завершении execution получает terminal status `Completed`.

## 6–13. Переходы и хранение

Состояние хранится не в памяти worker, а в event history на Temporal service. Worker crash/timeout не стирает историю: service выдаёт workflow task другому worker, который replay-ит детерминированный workflow code. Терминальные states включают Completed, Failed, Cancelled, Terminated, Continued-As-New и Timed Out. Код workflow должен быть deterministic; внешняя работа выносится в Activities. Человек запускает/cancel, service решает scheduling/replay. Нет prompts, browser gates, Git integration, product scope и cost policy. Артефакт — history, IDs/status и activity outputs; loop containment обеспечивается отдельными retry/timeouts и application logic, не durable execution itself.

## 14. Слабости

Durability сохраняет orchestration state, но не делает модельные решения правильными, не восстанавливает потерянный workspace без отдельного persistent storage и не является доказательством acceptance. Replay требует совместимой deterministic code; migration workflow definition — отдельная дисциплина.

## 15–16. WMS-применимость и вердикт

Взять архитектурный принцип: контрольная карточка и attempt ledger должны жить вне процесса агента, чтобы restart не превращал ночь в ручное расследование. Адаптировать лёгкой SQLite/Postgres state machine вместо немедленного Temporal: WMS сейчас нужен явный state/artefact ledger, а не новая тяжёлая платформа. Отвергнуть вывод «Temporal = железный pipeline» без Git/evidence/acceptance gates.

## 17. Evidence

- [Workflow Execution, IDs и event history](https://docs.temporal.io/workflow-execution).
- [Terminal states и replay/durability concepts](https://docs.temporal.io/workflow-execution#workflow-execution).
