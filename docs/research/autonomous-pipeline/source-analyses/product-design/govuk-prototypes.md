# GOV.UK — Making prototypes

## 1–2. Источник и доказательность

[Making prototypes](https://www.gov.uk/service-manual/design/making-prototypes), GOV.UK Service Manual, проверен 2026-08-24. E2: первичная практика, не правило для каждого diff.

## 3–5. Задача и путь

Prototype — способ ответить на конкретный design question, показать возможное user journey и собрать feedback, а не предварительная версия production UI. Руководство различает бумажные/low-fidelity и interactive/high-fidelity варианты; выбирается наименьшая fidelity, достаточная для проверяемой гипотезы.

## 6–13. Исполнимые pre-design gates

Перед любым новым mockup должна существовать `PROTOTYPE-INTENT`: question/hypothesis, целевой user task, decision that result will change, scope (существующий экран/новый flow), fidelity, test scenario и stop condition. **Новый модуль**: prototype обязателен, если неизвестна структура flow, навигация или состав данных. **Локальная правка**: prototype не обязателен; допустим annotated screenshot/HTML delta только если правка меняет понимание или действие. Код проверяет, что attached mockup соответствует declared affected zones; модель предлагает low-fi delta, не свободный total redesign. Артефакт — prototype link, scenario и feedback/evidence. Source не описывает prompts, Git, retries или acceptance browser tests.

## 14. Границы

Prototype не есть доказательство реализуемости API, correctness расчётов или browser acceptance. Высокая fidelity способна создать ложное ощущение готовности и потратить время до проверки идеи.

## 15–16. WMS-применимость и вердикт

Взять «question-first + lowest fidelity» как защиту от красивых, бессмысленных макетов. Адаптировать: новый отчёт получает low-fi table/filter/export arrangement, не Figma-перерисовку всего приложения; локальный fix меняет только свою зону. Вердикт: адаптировать, не вводить обязательный mockup для каждой задачи.

## 17. Evidence

- [Первичный материал](https://www.gov.uk/service-manual/design/making-prototypes).
