# Argo Workflows Automatic Pod Restarts

**Источник:** [Automatic Pod Restarts](https://argo-workflows.readthedocs.io/en/latest/pod-restarts/), проверено 2026-08-24. **Класс:** E2 official docs/spec; source repository [argo-workflows](https://github.com/argoproj/argo-workflows).

## Точная механика

Если pod fails **до того, как main container вошёл в Running**, controller распознаёт инфраструктурные причины (например eviction/DiskPressure/admission failure), удаляет pod, возвращает node в Pending и создаёт новый pod. Лимит `maxRestarts` (по docs default disabled, configurable cap) останавливает бесконечность. Status хранит `FailedPodRestarts` и message; метрика `pod_restarts_total` делает recovery наблюдаемым.

## Существенное разделение

Это не `retryStrategy`: restart безопасен потому, что пользовательский main process точно не начался. После запуска приложения нужен per-template retry, который может быть небезопасен для не-idempotent action. Следовательно, ошибка Docker/runner не должна автоматически превращаться в «перепиши код»: сначала машина доказывает, на какой стороне границы произошёл отказ.

## WMS-вердикт — взять принцип

Нужна аналогичная классификация: crash browser/container **до** теста/агента — restart environment с лимитом; падение уже начатого test/code action — не повторять слепо, сохранять evidence и идти в defined repair/blocked state. Argo не решает prompts, product scope или acceptance.

## Evidence

- [mechanism, counters, comparison](https://argo-workflows.readthedocs.io/en/latest/pod-restarts/)
- [retry field reference](https://argo-workflows.readthedocs.io/en/latest/fields/)
