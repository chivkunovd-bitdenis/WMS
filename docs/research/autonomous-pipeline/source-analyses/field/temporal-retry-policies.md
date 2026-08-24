# Temporal — retry policy как исполняемый контракт

## 1–2. Ссылка и доказательность

[Temporal Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies), official documentation, проверено 2026-08-24. E1 для заявленной API semantics, но не доказательство выбранной operational policy.

## 3–5. Задача и happy path

Temporal применяет retry policy к Workflow/Activity: Activity fails/timeout → service планирует следующую attempt по policy; success → Activity closes. Workflow может иметь свой Retry Policy при запуске как child/continue scenario. Компоненты: Temporal service, workflow execution, activity task, worker, event history и policy.

## 6–13. Механика

Policy задаёт initial interval, backoff coefficient, maximum interval, maximum attempts и non-retryable error types; без policy применяются defaults, различающиеся для Workflow и Activity. Retry decision детерминирован service по failure type и attempt history, не моделью. Артефакт/состояние — event history с attempts и failure. Prompts/browser/Git/scope отсутствуют. Recovery — новая scheduled attempt, но semantic correction кода не происходит. Loop containment — maximum attempts и non-retryable types; budget/cost не управляется автоматически.

## 14. Слабости

Wrong classification может повторять permanent code error или prematurely stop transient failure. Retry policy не заменяет idempotency: Activity может быть выполнена more than once. Source не обещает exactly-once external effects.

## 15–16. WMS-применимость и вердикт

Адаптировать сам контракт: таблица failure classes → retryable/non-retryable, cap, delay, evidence path должна быть в controller config. Взять separate `INFRA_TRANSIENT` от `CONTRACT_FAIL/TEST_FAIL`. Не брать Temporal как обязательную платформу и не трактовать retry как реwork модели.

## 17. Evidence

- [Retry Policy parameters и defaults](https://docs.temporal.io/encyclopedia/retry-policies).
- [Ошибки, которые не повторяются](https://docs.temporal.io/encyclopedia/retry-policies#non-retryable-errors).
