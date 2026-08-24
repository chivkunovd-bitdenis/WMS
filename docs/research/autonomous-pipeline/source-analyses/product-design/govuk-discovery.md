# GOV.UK — Discovery phase

## 1–2. Источник и доказательность

[How the discovery phase works](https://www.gov.uk/service-manual/agile-delivery/how-the-discovery-phase-works), GOV.UK Service Manual; проверен 2026-08-24, обновлён 2021-06-21. E2.

## 3–5. Задача и путь

Discovery отвечает, стоит ли вообще строить service, а не начинает build. Последовательность: задать goal → перевести полученное «решение» в problem → выделить assumptions и what is out → исследовать пользователей, контекст, ограничения и альтернативы → определить measure of success → решить proceed/stop. Источник прямо говорит, что остановка после discovery — не failure.

## 6–13. Исполнимые pre-design gates

Для **нового модуля/существенного изменения поведения** минимальный `DISCOVERY-CARD` должен иметь: исходную фразу владельца; problem statement без UI solution; user/outcome/evidence; value/cost-of-problem в доступной форме; hard constraints (данные, интеграции, законодательные/операционные); assumptions c планом проверки; alternatives including «не строить»/расширить существующий экран; proposed success metric; explicit out-of-scope. Controller может проверить schema и links; модель анализирует репо и формирует варианты; owner решает только substantive trade-off. После gate разрешён low-fidelity prototype, не production code. Нет prompts/Git/retry/browser mechanics в источнике.

## 14. Границы

Типичные 4–8 недель и public-service governance неприменимы буквально. Источник не обязывает делать discovery для одной колонки, copy или известного defect fix.

## 15–16. WMS-применимость и вердикт

Адаптировать к ночному pipeline как короткую, доказательную decision card: она препятствует ложному переходу от «сделай отчёт» к «рисуй dashboard». Для **локальной правки** gate заменяется scope card: user outcome остаётся прежним, затронутая зона и non-goals известны. Вердикт: взять decision semantics (proceed/stop), отвергнуть тяжёлую фазу/состав команды.

## 17. Evidence

- [Не начинать строить в discovery](https://www.gov.uk/service-manual/agile-delivery/how-the-discovery-phase-works#how-the-discovery-phase-works).
- [Reframe solution as problem; assumptions/out-of-scope](https://www.gov.uk/service-manual/agile-delivery/how-the-discovery-phase-works#define-the-problem).
- [Условия завершения discovery](https://www.gov.uk/service-manual/agile-delivery/how-the-discovery-phase-works#how-you-know-discovery-is-finished).
