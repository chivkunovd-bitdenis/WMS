# Playwright Trace Viewer — диагностический артефакт browser failure

## 1–2. Ссылка и доказательность

[Trace viewer](https://playwright.dev/docs/trace-viewer), official docs, проверено 2026-08-24. E1 для функции framework.

## 3–5. Задача и happy path

Trace recorder прикладывает к test attempt последовательность действий, DOM snapshots, network, console и metadata; viewer открывает её локально/через URL. Типичный путь: включить `trace: 'on-first-retry'` или `retain-on-failure` → test attempt завершается → trace zip сохраняется → человек или отдельный диагностический шаг читает его.

## 6–13. Механика

Создание trace и retention детерминированы конфигом; интерпретация причин — человек/модель. Артефакт — `.zip` trace, не текстовый verdict. Source не создаёт prompts, gates, Git isolation, resume или retry policy: он лишь связывается с retry lifecycle. Ограничение scope — один test attempt. Контроль бюджета — trace policy (`on`, `off`, `retain-on-failure`, `on-first-retry`) и storage, не token budget.

## 14. Слабости

Trace показывает наблюдаемое выполнение, но не доказывает бизнес-правильность и не заменяет живого оператора. При browser/process crash trace может отсутствовать или быть неполным; это нужно учитывать как отдельный failure mode.

## 15–16. WMS-применимость и вердикт

Взять: любой ночной browser failure должен публиковать trace/screenshot/video c SHA и attempt id, а rework prompt должен ссылаться на конкретный artifact. Адаптировать policy `retain-on-failure`, не записывать всё без лимита. Отвергнуть трактовку trace как acceptance proof.

## 17. Evidence

- [Что содержит trace и как его открыть](https://playwright.dev/docs/trace-viewer#recording-a-trace).
- [Конфигурация trace policy](https://playwright.dev/docs/trace-viewer#tracing-on-ci).
