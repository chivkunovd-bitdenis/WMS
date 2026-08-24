# Agentless — исходный код

**Источник/версия:** [Agentless `5ce5888b9f149beaace393957a55ea8ee46c9f71`](https://github.com/OpenAutoCoder/Agentless/tree/5ce5888b9f149beaace393957a55ea8ee46c9f71), HEAD 2026-08-24. **Класс:** E1. **Граница:** pipeline для SWE-bench patch generation/ranking, намеренно без интерактивного agent loop.

## Стадии и артефакты

Репозиторий разделяет localization (file → function/line), repair generation и patch validation/selection; промежуточные JSONL outputs образуют contract между стадиями. Код/commands находятся в [README](https://github.com/OpenAutoCoder/Agentless/blob/5ce5888b9f149beaace393957a55ea8ee46c9f71/README.md), [source tree](https://github.com/OpenAutoCoder/Agentless/tree/5ce5888b9f149beaace393957a55ea8ee46c9f71/agentless) и [tests](https://github.com/OpenAutoCoder/Agentless/tree/5ce5888b9f149beaace393957a55ea8ee46c9f71/tests).

## Код против модели

Модель производит ranked localization и patches по staged prompts; код ограничивает контекст найденными files/functions, применяет candidate patch и запускает test/harness. Это сильнее role report: следующий шаг получает typed persisted artifact, а не устный handoff. Git branches/PR, human approval, browser acceptance и durable controller recovery отсутствуют.

## Retry/loops/scope

Вместо открытой петли Agentless использует finite candidates и selection; это предел стоимости и scope. Но неверная localization отравляет repair; passing benchmark tests не доказывает продуктовую задачу. Механизм не классифицирует CI/Docker failures как отдельные причины.

## WMS-вердикт — адаптировать

Взять staged artifact schema и узкий impact set перед Dev: contract/allowed files → implementation → verifier. Не брать как замену UX/acceptance, и не использовать model localization как единственный scope authority.

## Evidence

- [pinned README](https://github.com/OpenAutoCoder/Agentless/blob/5ce5888b9f149beaace393957a55ea8ee46c9f71/README.md)
- [pinned implementation](https://github.com/OpenAutoCoder/Agentless/tree/5ce5888b9f149beaace393957a55ea8ee46c9f71/agentless)
- [pinned tests](https://github.com/OpenAutoCoder/Agentless/tree/5ce5888b9f149beaace393957a55ea8ee46c9f71/tests)
