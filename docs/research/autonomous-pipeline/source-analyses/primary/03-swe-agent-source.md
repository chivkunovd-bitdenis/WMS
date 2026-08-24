# SWE-agent — исходный код

**Источник/версия:** [SWE-agent `3ea751c087f32b16e039a2233dd6eefecef325d5`](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5), HEAD 2026-08-24. **Класс:** E1. **Граница:** issue-to-patch benchmark agent в изолированном окружении, не PR pipeline.

## Реальная машина состояний

Agent получает problem statement и environment; повторяет `model query → parse action → execute in environment → append observation`; parser error превращается в feedback/повтор model call. Exit action/submit образует patch; отдельный harness запускает verifier tests. Конфигурации и prompts лежат в [config](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5/config), runtime — в [source](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent), tests — в [tests](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5/tests).

## Решения и контракты

Модель выбирает shell-like action из prompt-defined interface; код парсит формат, лимитирует trajectory/стоимость по конфигу и изолирует environment. Benchmark task/test — машинный acceptance. Product scope, UX contract, review независимым агентом и Git merge отсутствуют.

## Retry/recovery/weaknesses

Есть repair feedback для неверных действий и budget/step limit; нет общего durable resume после runner/container crash в смысле workflow engine. `submit` означает кандидата на оценку, не доказанно хорошую фичу. Контекст растёт с observations; без отдельного scope gate агент может искать/править чрезмерно широко.

## WMS-вердикт — адаптировать только execution lane

Ценны строгий action grammar, isolated env и separation agent trajectory/test verifier. Для WMS добавить contract-before-code, file allowlist, staged Git commit и живую browser acceptance.

## Evidence

- [repository README](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md)
- [configuration directory](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5/config)
- [test suite](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5/tests)
