# OpenAI Agents SDK Python — глубокая карточка

**Источник/проверка:** [repository at `fe45b415ee05479725cd6fb20a51c0d5cd73b3c1`](https://github.com/openai/openai-agents-python/tree/fe45b415ee05479725cd6fb20a51c0d5cd73b3c1), HEAD проверен 2026-08-24. **Класс:** E1 (код + тесты). **Граница:** SDK для запуска одного/нескольких LLM-агентов; это не SDLC-оркестратор и не CI.

## Состояние и happy path

`Runner.run` исполняет активного агента, добавляет model output/tool output в историю, исполняет tools, либо завершает output, либо меняет active agent при handoff. Механика и ограничитель turn count описаны в [runner source](https://github.com/openai/openai-agents-python/blob/fe45b415ee05479725cd6fb20a51c0d5cd73b3c1/src/agents/run.py) и [tests](https://github.com/openai/openai-agents-python/tree/fe45b415ee05479725cd6fb20a51c0d5cd73b3c1/tests). Handoff — модельное решение через tool call; исполнение функции/валидация схемы — код.

## Контракты, гейты, восстановление

- `Agent` хранит instructions, tools, handoffs, output type и guardrails; [API/docs](https://openai.github.io/openai-agents-python/).
- Function-tool schema и structured output дают машинно валидируемый I/O контракт; input/output guardrail может остановить run. Это гейт содержимого, не acceptance UI/CI.
- `max_turns` ограничивает петлю; исключение `MaxTurnsExceeded` — terminal failure, а не автоматический retry.
- Sessions могут сохранить историю между запусками, но транзакционный workflow state, классификация infra errors, повторный запуск job и Git/branch ownership не предоставляет SDK.

## Prompts/полномочия

Реальный prompt — `Agent.instructions`, передаваемый модели. SDK не предписывает Product/UX/Dev роли и не поставляет WMS-контрактов; handoff лишь переключает активного агента. Следовательно, роль нельзя считать гейтом, пока внешний код не проверяет её артефакт.

## WMS-вердикт — адаптировать

Брать typed tools/output, guardrail и `max_turns` как низкоуровневый agent runtime. Не брать как конвейер: поверх него нужны durable card state, запрещённые file scopes, CI/browser acceptance и отдельные retry-классы.

## Evidence

- [README: primitives](https://github.com/openai/openai-agents-python/blob/fe45b415ee05479725cd6fb20a51c0d5cd73b3c1/README.md)
- [runner implementation](https://github.com/openai/openai-agents-python/blob/fe45b415ee05479725cd6fb20a51c0d5cd73b3c1/src/agents/run.py)
- [guardrails docs](https://openai.github.io/openai-agents-python/guardrails/)
