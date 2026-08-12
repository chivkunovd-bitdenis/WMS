# Шаблон находки полного ревью WMS

Один файл — одно наблюдаемое расхождение. Пустое обязательное поле означает `EVIDENCE_MISSING`; такая находка не попадает в приоритетную очередь.

## Паспорт

- Finding ID:
- Title — пользовательский результат, а не предполагаемая причина:
- Class: `BUG` / `PRODUCT_GAP` / `SECURITY` / `RELIABILITY` / `CONTRACT_CONFLICT` / `UNKNOWN` / `ENHANCEMENT_OUT_OF_SCOPE`
- Severity: P0 / P1 / P2 / P3 / not ranked
- Area / scenario ID:
- First reviewer / independent verifier:
- Environment and SHA:
- Role / tenant / seller test IDs:
- WB mode: emulator / test / live / N/A

## Ожидаемое поведение

- Источник правды, точный раздел или официальная ссылка:
- Дата проверки внешнего источника:
- Короткое ожидаемое поведение:

## Фактическое поведение и воспроизведение

- Предусловия и физический контекст склада:
- Шаги от чистого состояния:
- Что видно пользователю:
- Что произошло с данными, задачей, печатью или WB:
- Повторяемость: attempts / reproduced:

## Доказательства

- `before` screenshot:
- `action` screenshot:
- `result` screenshot:
- `reload` screenshot:
- negative/failure screenshot:
- sanitized request/response or trace ID:
- DB/read-back proof with non-secret IDs:
- relevant logs without secrets:
- code path `file:line`:
- existing automated test and its result:

## Ущерб и граница

- Кто страдает и как часто:
- Результат: неверные данные / тупик / двойная операция / утечка / лишний труд / UX noise:
- Workaround and its cost:
- Почему это дефект, а не новая функция:
- Что точно не входит в эту находку:

## Анализ причины

- Proven root cause / hypothesis / unknown:
- Evidence separating cause from correlation:
- Retry, concurrency and recovery implications:
- Tenant/seller/security implications:

## Критерий закрытия без проектирования решения

- Given:
- When:
- Then — visible result:
- And — data/WB result:
- Negative / retry / isolation requirement:

## Проверка минимальности будущего исправления

- Можно ли восстановить инвариант существующими сущностями и экраном?
- Какое минимальное изменение поведения требуется?
- Какая новая сущность/настройка предлагалась и почему она пока запрещена?

## Вердикт оркестратора

- Accepted / evidence missing / duplicate / conflict / out of scope:
- Duplicate of:
- Second reproduction for P0/P1:
- Queue status:
