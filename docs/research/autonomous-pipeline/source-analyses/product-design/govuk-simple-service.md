# GOV.UK Service Standard point 4 — Make the service simple to use

## 1–2. Источник и доказательность

[Point 4: Make the service simple to use](https://www.gov.uk/service-manual/service-standard/point-4-make-the-service-simple-to-use), GOV.UK Service Manual, проверен 2026-08-24. E2: первичный service standard; не набор визуальных правил.

## 3–5. Задача и путь

Standard требует, чтобы service позволял пользователям успешно завершить нужное дело, а не просто получить «современный» интерфейс. Движение: понять end-to-end task и context → сделать нужные действия и информацию понятными → тестировать с users → итеративно упрощать.

## 6–13. Исполнимые pre-design gates

Перед дизайном фиксировать `TASK-TO-UI MAP`: user decision/action; ровно нужные fields/metrics; primary path; empty/error states; что намеренно не показывается; how usability will be observed (scenario + observable completion/error). Для **нового модуля** это полный gate и usability evidence до completion. Для **локальной правки** достаточно проверить, что элемент помогает текущему task и не ухудшает основной path; не нужно открывать новый research cycle. Машина может валидировать явное соответствие visible element → requirement, модель — составить map, пользователь/оператор — судить фактическую пригодность. Prompts, retry/Git отсутствуют в источнике.

## 14. Границы

«Simple» не означает мало строк, мало цветов или отказ от нужных operational data. Источник не выбирает dashboard/table/card и не устанавливает единый UI kit.

## 15–16. WMS-применимость и вердикт

Взять как element-justification gate: для отчёта по остаткам любая колонка/карточка/диаграмма должна отвечать на именованное решение оператора. В WMS сохраняются сложные данные, если они необходимы task; удаляется декоративный UI. Вердикт: адаптировать как таблицу соответствий, не как субъективную роль «дизайнера простоты».

## 17. Evidence

- [Service Standard point 4](https://www.gov.uk/service-manual/service-standard/point-4-make-the-service-simple-to-use).
