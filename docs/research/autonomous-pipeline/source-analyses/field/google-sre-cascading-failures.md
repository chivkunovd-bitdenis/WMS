# Google SRE — каскадные отказы и retry budgets

## 1–2. Ссылка и доказательность

[Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/), Google SRE Book, проверено 2026-08-24. E2: первичное инженерное руководство, основанное на production practice; не код и не agent-specific case.

## 3–5. Задача и happy path

Материал рассматривает сервис A, который зависит от B. Нормальный путь — запрос получает ответ в пределах deadline. При росте latency/ошибок A должен сохранить способность обслуживать полезную работу, а не создать очередь retry запросов, исчерпать ресурсы B и уронить всё дерево.

## 6–13. Механика

Переходы имеют условия: latency выше deadline/ошибка → controlled retry только в лимите; overload → load shedding/admission control; exhausted budget → fail fast с наблюдаемым error. Техники: timeouts, backoff, jitter, retry budget, circuit breakers, graceful degradation. Код/infra исполняют счётчики и ограничения; человек определяет SLO/допустимые ошибки. Нет prompts, schemas, Git, UI/browser acceptance или durable resume. Артефакты — метрики, error rate, saturation/queue и reason rejection. Loop containment — общий retry budget, а не самостоятельный счётчик каждого caller.

## 14. Слабости

Это распределённые сервисы, не тестовый runner. Circuit breaker или load shedding без правильной терминальной семантики может просто спрятать ночной failure, поэтому WMS обязан сохранить blocker artifact.

## 15–16. WMS-применимость и вердикт

Адаптировать: controller держит общий лимит ночных повторов по task и по dependency, прекращает попытки при повторе одной signature и сохраняет `BLOCKED_INFRA` с logs. Взять fail-fast и evidence-first, отвергнуть бесконечные локальные retries ролей.

## 17. Evidence

- [Глава SRE Book](https://sre.google/sre-book/addressing-cascading-failures/) — retry amplification, backoff, load shedding, circuit breaking.
