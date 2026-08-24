# LangGraph Durable Execution

**Источник:** [Durable execution](https://langchain-ai.github.io/langgraph/concepts/durable_execution/), [interrupts](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/), проверено 2026-08-24. **Класс:** E2 docs; runtime source доступен как [E1](https://github.com/langchain-ai/langgraph).

## Состояние и happy path

Graph выполняет node; checkpointer сохраняет state/checkpoint; при resume graph replay-ит entrypoint, восстанавливая завершённые task outputs. Непредсказуемая работа/side effect обязаны быть заключены в task: иначе replay повторит запись/API call. `interrupt()` сохраняет state, возвращает payload внешнему вызывающему и ждёт `Command(resume=...)` с тем же thread id.

## Переходы и ownership

Код задаёт nodes, edges, retry policy, checkpointer и serializable state. Модель — только содержимое agent node. Человек решает значение resume payload. Документация прямо предупреждает, что node при resume начинается с начала: значит вызовы до interrupt должны быть idempotent или task-encapsulated.

## Гейты/recovery/limits

Checkpoint и task caching обеспечивают recovery, а retry policy — node-level retry. Однако LangGraph не классифицирует WMS Docker/test failures за пользователя, не содержит Git worktree/merge isolation, UI acceptance или finite product roles. Loop/cost limit должен быть явным state/counter outside prompt.

## WMS-вердикт — взять как семантический образец

Нужны те же: persisted card state, idempotent side effects, exact resume cursor, structured interrupt. Реализовать можно без добавления LangGraph; ключ — не повторять agent edit/commit после падения контроллера.

## Evidence

- [durability and determinism](https://langchain-ai.github.io/langgraph/concepts/durable_execution/)
- [human interrupt/resume API](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/)
- [source/tests](https://github.com/langchain-ai/langgraph)
