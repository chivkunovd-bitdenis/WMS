# Claude Code Hooks — глубокая карточка

**Источник/проверка:** [официальная документация Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks), доступ 2026-08-24. **Класс:** E2: спецификация автора; открытого production runner для независимой построчной проверки нет.

## Состояние и переходы

Hook запускается на определённом lifecycle event (например, до/после tool use, stop, session start/end). Код hook получает JSON event; exit/status или structured decision влияют на продолжение: разрешить, заблокировать, дать feedback, либо зафиксировать факт. Это детерминированный переход вокруг модельного tool call, а не самостоятельная роль.

## Контракты и recovery

- Схема события/матчинг по tool name — машинный contract; shell command, prompt hook или HTTP hook — исполняемая policy.
- Pre-tool hook может остановить опасную/внескоуповую операцию до изменения; post-tool годится для запуска invariant/test evidence.
- Документация не обещает durable checkpoint, классификацию Docker/CI отказов, автоматическую повторную попытку или Git merge semantics. Ошибка hook должна быть спроектирована локально как deny/fail-open и наблюдаема.

## Prompt и escalation

Prompt hook может вернуть модели контекст, но сам по себе не доказывает, что модель его исполнит. Для WMS человек должен получать interrupt только после исчерпания определённой recovery-policy; такой роутинг Hooks не поставляет.

## WMS-вердикт — взять узко

Hooks подходят для жёстких доизменяющих гейтов: наличие наряда, allowlist файлов, запрет broad diff; и для послеизменяющих — invariant/receipt. Нельзя ими заменить state machine или судью в браузере.

## Evidence

- [Hooks reference](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [Settings/permission model](https://docs.anthropic.com/en/docs/claude-code/settings)
- [Subagents scope](https://docs.anthropic.com/en/docs/claude-code/sub-agents)
