# GOV.UK — Learning about users and their needs

## 1–2. Источник и доказательность

[GOV.UK Service Manual: Learning about users and their needs](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs), проверен 2026-08-24, опубликован 2016-04-04, обновлён 2017-03-23. E2: первичное руководство владельца крупного digital-service стандарта; не полевой эксперимент и не WMS-спецификация.

## 3–5. Задача и рабочий путь

Источник требует до проектирования узнать, кто использует сервис, чего пытается добиться, как делает это сейчас, где испытывает проблемы и какой outcome нужен. Путь: existing evidence/наблюдение/интервью → сформулированная user need → validation/refinement → user stories с traceability. Нужда описывается от первого лица: «I need… so that…», а не как заранее выбранный экран или кнопка.

## 6–13. Исполнимые pre-design gates

До макета **нового модуля** допустим переход только при карточке: named user/operator и его trigger; job/outcome; минимум один evidence link (analytics, текущий экран/процесс, операторский сценарий) либо явно маркированное assumption; существующий workaround/friction; одна мера успеха; список не-целей. Код проверяет наличие полей/links, модель может извлечь их из источников и предложить формулировку; человек решает спорный бизнес-priority. Артефакт — `USER-OUTCOME.md`/структурированная contract card. Prompts, browser/Git/retry не входят в источник. Assumption не должна выдаваться за evidence; при недостатке evidence нужен research subtask, а не «красивый» дизайн.

## 14. Границы

GOV.UK требует continuous research и учитывает всех типов пользователей, включая support staff. Для WMS это принцип, но не требование проводить полноценное интервью перед текстовой правкой. Источник не даёт минимального sample size и не выбирает UI.

## 15–16. WMS-применимость и вердикт

Взять gate полностью для нового отчёта/модуля (например, остатки и движения): до экрана зафиксировать оператора, решение, показатели и evidence. Для **локальной правки существующего экрана** — облегчённо: ссылка на уже принятую потребность/contract плюс изменение outcome; новый research не обязателен, если смысл экрана не меняется. Вердикт: адаптировать как короткий mandatory card, не как отдельную постоянную роль.

## 17. Evidence

- [Что исследовать в discovery](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs#when-to-research).
- [Мнения без user evidence — assumptions](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs#how-to-research).
- [Формат и критерии user need](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs#writing-user-needs).
