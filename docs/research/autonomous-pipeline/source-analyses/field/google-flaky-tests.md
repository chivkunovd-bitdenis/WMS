# Google Testing Blog — Flaky Tests at Google

## 1–2. Ссылка и доказательность

[Flaky Tests at Google and How We Mitigate Them](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html), Google Testing Blog, 2016-05-16; проверено 2026-08-24. E2: первичное инженерное описание внутренней практики Google, не открытый код и не agent-specific material.

## 3–5. Задача, компоненты, путь

Задача — сохранять signal CI, когда тест периодически меняет результат при том же code/environment. Описаны Google test infrastructure, presubmit/postsubmit, automated reruns, flaky-test detection и ownership. Happy path: тест стабильно проходит; при несогласованном повторе инфраструктура распознаёт flake, а команда получает данные для исправления.

## 6–13. Механика

Код/инфраструктура повторно исполняет тест, агрегирует историю и маркирует instability; человек владеет исправлением причины. Это не «retry до зелёного»: повтор является диагностическим измерением. Source не задаёт prompts, agent schemas, Git isolation, browser acceptance или конкретный state-machine API. Артефакты — test result history и flaky classification. Budget/loop limit количественно не описан; главное ограничение — rerun может показывать симптом, а не исправлять nondeterminism.

## 14. Слабости

Статья старая и описывает Google-scale environment, без public implementation detail. Не переносит автоматически критерий flaky на WMS; повторяющийся failure может быть data bug или инфраструктурой.

## 15–16. WMS-применимость и вердикт

Адаптировать: результат browser/test gate хранит attempt history, command, SHA и классификацию; `pass after retry` остаётся отдельным статусом `flaky-suspected`, не равен чистой приёмке. Взять принцип диагностики и ownership, отвергнуть бесконечные retries как способ «озеленить ночь».

## 17. Evidence

- [Основная статья](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) — определение flaky и описание rerun/mitigation.
