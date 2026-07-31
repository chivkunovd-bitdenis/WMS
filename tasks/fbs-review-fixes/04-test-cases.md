# 04 — Тест-кейсы

## Кейсы
| # | TC-ID | Что проверяем | Вход / предусловие | Ожидаемый результат | Из критерия |
|---|-------|---------------|--------------------|-----------------------|-------------|
| 1 | TC-NEW-FBS-FIX-001 | Отмена в assembling | 2 заказа в supply, assembling, packaging task | После cancel одного: supply_id снят, qty_total-1, promote возможен | 03 §001 |
| 2 | TC-NEW-FBS-FIX-001 | Отмена последнего | 1 заказ в supply assembling | supply → draft | 03 §001 neg |
| 3 | TC-NEW-FBS-FIX-002 | Конкурентный резерв | stock=1, 2 orders, nested sessions | 1 reserved, 1 no_stock | 03 §002 |
| 4 | TC-NEW-FBS-FIX-003 | Пагинация синка | 501 new orders, mock WB status | 501-й (старый) обновлён | 03 §003 |
| 5 | TC-NEW-FBS-FIX-004 | PACKED + marking | honest_sign product, sgtin new→ok | packed только после ok | 03 §004 |

## Крайние случаи / негатив
| # | Сценарий | Ожидаемое поведение |
|---|----------|--------------------|
| N1 | Cancel заказа без supply | только release reservation |
| N2 | IntegrityError при резерве existing | не роняет sync tick |

## Где живут тесты
- `backend/tests/test_fbs_review_fixes.py` (новый файл)
- расширение `test_fbs_cancellations.py` при необходимости
