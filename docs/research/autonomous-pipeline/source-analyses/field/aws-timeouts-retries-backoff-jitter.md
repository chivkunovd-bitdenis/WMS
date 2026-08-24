# AWS Builders Library — timeouts, retries, backoff with jitter

## 1–2. Ссылка и доказательность

[Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/), AWS Builders Library; проверено 2026-08-24, страница сейчас перенаправляет на builder.aws.com. E2: первичное инженерное описание Amazon, не agent pipeline и не public code.

## 3–5. Задача и happy path

Задача — не превратить частичный dependency failure в каскадный outage. Клиент вызывает downstream service с timeout; при временной ошибке ограниченно повторяет idempotent operation с backoff+jitter; успешный ответ завершает операцию. Компоненты: client, dependency, timeout, retry policy, load/latency и idempotency.

## 6–13. Точные переходы и границы

Timeout — продуктовый контракт, выбираемый по latency distribution и допустимой false-timeout rate. После timeout/error retry разрешён только если операция safe/idempotent и попытки/budget остались; delay растёт до cap и random jitter разносит клиентов. На вершине call stack обычно лучше одно место retries, иначе multiplication across layers усиливает нагрузку. Code принимает timeout/count/backoff decision; человек задаёт policy, модель тут не нужна. Артефакты: error/attempt metrics и idempotency token. Source не включает prompts, browser, Git или state-machine resume. Loop containment — cap attempts, capped backoff и throttling/token bucket.

## 14. Слабости

Статья предупреждает, что retry может ухудшить overload и что timeout не гарантирует отсутствие side effect. Она не даёт готовой классификации «test vs Docker vs code» и не определяет acceptable budget для WMS.

## 15–16. WMS-применимость и вердикт

Адаптировать только orchestration calls: transient network/runner polling можно повторять с attempt cap, jitter и evidence; code/test failure не ретраить по этой логике. Взять единый retry owner controller, чтобы developer, reviewer и CI не делали вложенных retries. Не брать blanket retry для Git push/deploy/API с побочными эффектами без idempotency.

## 17. Evidence

- [Первичный URL / актуальный redirect](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/).
- [Материал AWS Builders Library](https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter) — timeout, retry multiplication, backoff/jitter и idempotency.
