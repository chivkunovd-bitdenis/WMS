# AWS Step Functions — error handling

**Источник:** [Handling errors](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html), проверено 2026-08-24. **Класс:** E2 official specification/docs. **Граница:** durable cloud state machine, не coding agent.

## Состояния и переходы

ASL state (`Task`, `Choice`, `Pass`, `Wait`, `Parallel`, `Map`, `Succeed`, `Fail`) определяет детерминированный graph. На task error runtime сопоставляет error name с ordered `Retry` rules; при исчерпании attempts применяет `Catch`, который меняет input/переходит в named recovery state; иначе execution fails. `redrive` перезапускает failed execution с учётом документированных reset правил retry counters.

## Что код, что модель/человек

State graph, error matcher, interval/backoff/max attempts и terminal states — машинная политика. Внутри Task можно вызвать модель, но она не должна решать, повторять ли Docker, тест или validation error. Человек может быть интегрирован callback task token, но это отдельный явный state.

## Ограничения и WMS

Сильный переносимый паттерн: taxonomy `infra transient → bounded retry`, `expected validation → repair state`, `contract/scope failure → terminal blocked`, `unknown → evidence + escalation`. Step Functions не поставляет prompts, source diff guards, Git integration или browser judge. **Вердикт: взять state/error semantics, не AWS как обязательную платформу.**

## Evidence

- [error names, Retry/Catch, redrive](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [callback tokens](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html#connect-wait-token)
