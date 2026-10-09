# WMS-716–720 · Отчёт тестировщика, тесты до кода · 09.10.2026

Результат локален и не сохранён коммитом. Commit/push не выполнялись по прямому
поручению ведущего. Этот отчёт не является ревью, приёмкой, CI или доказательством
исправления продукта. WMS-716, WMS-717 и WMS-719 имеют адресный автоматический
контракт; этап WMS-718 и WMS-720 остановлен из-за требований к настоящей раскладке
браузера при запрете браузерной автоматизации.

## Исходное состояние и среда

- Каталог: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms716-720-orders-list`.
- Ветка: `feat/wms716-720-fbs-orders-list`.
- Исходный HEAD: `c6d38003be99704c2239c5a834befcd0e0f501a2`; рабочее дерево было чистым.
- Прочитаны целиком AGENTS.md, wms-test-writer/SKILL.md, требования пяти задач
  и failure-cases.md. Правила совпадают с доступной локальной копией origin/etalon.
  Fetch запрещён средой: запись FETCH_HEAD лежит вне разрешённого worktree;
  актуальность remote не подтверждена. Новая ветка и checkout не создавались.
- node_modules подключён. Python взят из указанного ведущим backend/.venv.
  Pytest использовал отдельную SQLite, создаваемую conftest; её временные файлы
  очищены средой тестирования. До первого запуска известных красных проверок
  этого пакета не было.
- Два существующих теста `test_fbs_worklist_search.py` прошли. Четыре существующих
  теста `FbsChips.test.ts` прошли. Это подтверждает доступность среды, но не
  является новым контрактом WMS-716–720.
- Первые DOM-запуски без отсечения соседних закрытых рабочих пространств
  не завершились за время диагностики и были прерваны. Исправлена тестовая среда:
  закрытые диалоги и рабочие пространства заменены пустыми компонентами.
  Сам экран, строки, FbsChips, ProductPhotoThumb и сетевой fbsApi не подменяются.
  После этого адресные прогоны завершаются. Окончательные результаты ниже
  получены без пропусков и необработанных ошибок тестовой среды.

## Итог запусков и доказательства

Финальный адресный Vitest: **45 случаев, 41 красный, 4 зелёных, 0 пропусков**.
Pytest новых файлов: **6 красных WMS-716 и 1 зелёный WMS-719**.
После уточнения тестовых данных повторены только C3–C5 WMS-716: все три снова
красные на отсутствующем API чисел, подготовка данных и доступ сотрудника исправны.
Ruff двух новых Python-файлов и TypeScript-проверка проходят.

Красный тест нового поведения доказывает отсутствие поведения на текущем коде.
Если сценарий останавливается на первой предпосылке (например, API ещё нет),
последующие шаги **blocked**, а не приняты: полный объём, фильтры, задержанные
ответы и восстановление предстоит успешно пройти на реализации с теми же
ожиданиями. Ни 404, ни отсутствие первого числа не названы доказательством
успешности оставшихся шагов.

Польза всех пяти зелёных новых случаев доказана временной порчей продукта:

| Проверка | Временная ошибка | Содержательное падение |
|---|---|---|
| WMS-717 C4, отмена | «—» заменено на BROKEN-CANCELLED | Получена другая подпись отменённого заказа |
| WMS-717 C6, соседний вызов | Оставшиеся часы подписаны как минуты | `49 минут` вместо `49 ч` |
| WMS-719 C4, экспорт | SKU удалён из построения Excel | В содержимом Blob отсутствует DISTINCT-SKU-719 |
| WMS-719 C5, структура | «Маршрут сдачи» заменён другим названием | Нет обязательной колонки в DOM |
| WMS-719 C4, сервер | SKU заменён на null в _map_order | Ответ содержит null вместо исходного SKU |

Временные изменения откатились в finally; все три продуктовых файла восстановлены
байт в байт. Зелёные случаи затем снова прошли на восстановленном коде.

## WMS-716 · числа вкладок и селлеров

Файлы:

- `backend/tests/test_wms716_fbs_counts.py`
- `frontend/src/screens/v2/FfFbsOrdersScreen.wms716.dom.test.tsx`
- `docs/requirements/WMS-716.md` — заполнены только поля «Тест» C1–C7.

В автоматическом контракте выбран технический способ чтения:
`GET /operations/fbs-orders/counts` с теми же фильтрами и status_group текущей
вкладки. Ответ содержит `tabs: {new, active, delivery}` и `sellers: {seller_uuid:
count}` для текущей вкладки. Это форма исполняемого тестового контракта, а не
новое бизнес-требование аналитика. Хранимый счётчик не вводится. И серверные,
и DOM-тесты используют одну форму ответа; менять бизнес-ожидания при реализации
нельзя.

Серверные C1/C2/C3/C4/C5/C7 красные: маршрут чисел отсутствует, получен 404.
DOM C1/C4/C6/C7 красные: нет чисел или запросов их чтения; при ошибке отсутствующего
чтения не возникает ожидаемая ошибка. C2 создаёт 501 новый заказ, 501 локальную
поставку, двухпозиционный Ozon с 12 единицами, ссылку сборочного задания и внешний
заказ; существующие первые страницы действительно ограничены 500 строками.
В C5 сотрудник с доступом только к A заранее проходит существующий worklist даже
при запросе чужого селлера: возвращаются только его два заказа. C3 отдельно
различает действующий склад на «Новых» и неактивный склад в контексте поставок.

Зелёных новых тестов нет. Противоречий между проверками и бизнес-требованиями
не выявлено. Экранная C8 остаётся без ссылки «Тест».

Имена серверных тестов:

- `test_c1_counts_orders_in_three_tabs_not_supply_rows` — красный, API возвращает 404.
- `test_c2_full_volume_unique_ozon_positions_and_assembly_members` — красный, API возвращает 404.
- `test_c3_filters_use_full_target_list_and_whole_matched_supply` — красный, API возвращает 404.
- `test_c4_seller_counts_replace_selected_seller_and_include_zero` — красный, API возвращает 404.
- `test_c5_tenant_and_employee_seller_scope_cannot_be_widened` — красный, API возвращает 404.
- `test_c7_recounts_changed_data_without_writes_to_orders_stock_or_reserve` — красный, API возвращает 404.

Имена DOM-тестов:

- `C1 displays counts on exactly three tabs, including successful zero and refresh` — красный.
- `C4 shows other sellers and selectable zero after selecting A and changing tabs` — красный.
- `C4 keeps the warehouse reset when changing seller and reads counts after the reset` — красный.
- `C6 discards delayed A after B and hides old counts while the new context loads` — красный.
- `C6 distinguishes first failure from zero and restores counts after retry` — красный.
- `C6 retains successful counts only for the same context during failed refresh` — красный.
- `C7 refreshes changed counts manually, on the background tick and on visibility return` — красный.

## WMS-717 · прошедшее время

Файлы:

- `frontend/src/screens/v2/FfFbsOrdersScreen.wms717.dom.test.tsx`
- `docs/requirements/WMS-717.md` — заполнены только поля «Тест» C1–C6.

24 случая: 22 красных, 2 зелёных. На текущем коде считаются оставшиеся часы
вместо возраста от created_at_wb; после срока WB остаётся одно «Просрочен»,
у Ozon плашка исчезает. Некорректный срок даёт `NaN ч`, известное начало без
срока не вычисляется. Тесты проверяют серверную основу при календарном сдвиге
компьютера и TZ America/Los_Angeles, минутные переходы через 24/120 часов,
125 ч 07 мин, старые пороги цвета, отсутствие новых запретов выбора,
пустые/будущие даты, тики, скрытую страницу, отказ чтения и повторное открытие.

Зелёные C4 отмены и C6 соседнего вызова сохранились и доказаны порчей выше.
При проверке соседнего вызова используется настоящий DeadlinePill с прежними
аргументами рабочего пространства поставки; само закрытое рабочее пространство
не принимается в этом DOM-наборе. Его живой экран остаётся частью последующей
приёмки. Противоречий не выявлено; ручная C7 без ссылки.

Имена DOM-тестов:

- `C1 starts at 2 ч 05 мин from marketplace creation despite client calendar skew` — красный.
- `C1 displays 125 ч 07 мин without wrapping elapsed hours` — красный.
- `C1 carries elapsed minute 59 without resetting days or the 120-hour limit` — красный.
- `C1 carries elapsed minute 1439 without resetting days or the 120-hour limit` — красный.
- `C1 carries elapsed minute 7199 without resetting days or the 120-hour limit` — красный.
- `C2 retains WB urgency at 49 hours left while keeping numeric age` — красный.
- `C2 retains WB urgency at 48 hours left while keeping numeric age` — красный.
- `C2 retains WB urgency at 13 hours left while keeping numeric age` — красный.
- `C2 retains WB urgency at 12 hours left while keeping numeric age` — красный.
- `C2 retains WB urgency at 0 hours left while keeping numeric age` — красный.
- `C2 retains WB urgency at -1 hours left while keeping numeric age` — красный.
- `C2 crosses the WB deadline without replacing numeric age or blocking selection` — красный.
- `C3 shows Ozon processing age with deadline offset 1 hours` — красный.
- `C3 shows Ozon processing age with deadline offset -1 hours` — красный.
- `C4 handles absent creation/deadline without inventing an age` — красный.
- `C4 handles null creation/deadline without inventing an age` — красный.
- `C4 handles invalid creation/deadline without inventing an age` — красный.
- `C4 handles future creation/deadline without inventing an age` — красный.
- `C4 handles no deadline creation/deadline without inventing an age` — красный.
- `C4 handles invalid deadline creation/deadline without inventing an age` — красный.
- `C4 retains dash for cancelled orders` — зелёный.
- `C5 advances offline, catches up after hidden time and survives errors, refresh and reopening` — красный.
- `C6 preserves the shared deadline-only call used by the supply workspace` — зелёный.
- `C6 preserves the supply shipment date column while orders show elapsed age` — красный.

## WMS-718 · уползающий заголовок

Новых тестовых файлов нет. `docs/requirements/WMS-718.md` не изменён.

C1 требует воспроизведения исходного дефекта на экране; этого доказательства
сейчас нет. C2 прямо требует браузерную автоматизацию, C3–C5 — координаты,
раскладку и перекрытия. Геометрическая часть C6 тоже не доказывается jsdom:
DOM может проверить смену данных, но не сохранение положения и прокрутки.
jsdom не рассчитывает настоящие размеры и положение липкой шапки. Подмена
getBoundingClientRect ожидаемыми координатами проверяла бы фикстуру.

Задача остановлена по п.7 поручения и правилу навыка «Если Cn … автоматом
недоказуема … останови задачу до решения». По указанию ведущего её геометрия
остаётся ручной работой, не имитируется DOM-тестом. Изменять записанные
аналитиком классы C2–C5 и текст C6 тестировщик не уполномочен: в рамках этого
этапа разрешён только столбец «Тест». Ведущему/аналитику требуется согласовать
эти классы с запретом браузерных тестов. Все ссылки оставлены пустыми;
закрепление CSS не объявлено исправлением исходного дефекта.

## WMS-719 · размер на месте SKU

Файлы:

- `frontend/src/screens/v2/FfFbsOrdersScreen.wms719.dom.test.tsx`
- `backend/tests/test_wms719_fbs_size_search.py`
- `docs/requirements/WMS-719.md` — заполнены только поля «Тест» C1–C5.

DOM: 14 случаев, 12 красных, 2 зелёных. Сервер: один зелёный C4.
C1 падает на оставшейся колонке SKU в обеих ветвях; C2 — на общем размере товара
вместо S/XL/«—» позиций; C3 — на пустых/пробельных строках и объединении данных
позиций через общий product.size. Покрыты обе ветви таблицы и WB/Ozon без позиций,
отдельные отсутствующий/null/пустой/пробельный размер позиции и одинаковые размеры.

Зелёные C4 проверяют настоящий сетевой адаптер, ввод поиска, выбор чекбокса,
содержимое реального Excel Blob и повторное чтение; серверный C4 подтверждает
идентичность заказа, SKU, размер, неизменность остатков/резерва/движений.
C5 сохраняет ключевые колонки заказов, «Статус» вне «Новых» и таблицы поставок.
Польза всех зелёных случаев доказана порчей, затем восстановлена.
Противоречий не выявлено; ручная C6 без ссылки. Наличие вкладки «Просрочены»
тестами не требуется, чтобы не мешать WMS-692.

Имена серверных тестов:

- `test_c4_sku_search_preserves_identity_size_inventory_and_reserve` — зелёный, польза доказана временным null вместо SKU.

Имена DOM-тестов:

- `C1 replaces SKU with one size column on Новые` — красный.
- `C1 replaces SKU with one size column on Отменённые` — красный.
- `C2 preserves each Ozon position size and order after refresh on Новые` — красный.
- `C2 preserves each Ozon position size and order after refresh on Отменённые` — красный.
- `C3 uses product size or dash without positions for wb on Новые` — красный.
- `C3 uses product size or dash without positions for ozon on Новые` — красный.
- `C3 uses product size or dash without positions for wb on Отменённые` — красный.
- `C3 uses product size or dash without positions for ozon on Отменённые` — красный.
- `C3 keeps equal sizes as separate Ozon position values on Новые` — красный.
- `C3 keeps equal sizes as separate Ozon position values on Отменённые` — красный.
- `C3 normalizes unknown sizes independently for Ozon positions on Новые` — красный.
- `C3 normalizes unknown sizes independently for Ozon positions on Отменённые` — красный.
- `C4 preserves SKU search, selection and real Excel export after refresh` — зелёный.
- `C5 keeps core order columns, status outside New and the supply table` — зелёный.

## WMS-720 · фото на высоту строки

Новых тестовых файлов нет. `docs/requirements/WMS-720.md` не изменён.

C1 прямо требует измерить фото и строку после браузерной раскладки, проверить
изменение высоты длинной строки и отсутствие бесконечного роста. C3 требует
геометрических измерений и проверки искажения изображения. Эти результаты
jsdom не рассчитывает. В C2/C4/C5 также есть геометрия наряду с поведением,
которое отдельно возможно проверить в DOM. C7 содержит доступные DOM/API
проверки соседей и неизменности данных, но по п.7 задача остановлена уже на
обязательной C1; частичный набор не выдан за контракт всей задачи.

Противоречие относится к классу/способу доказательства, а не к требованию
владельца: нужны настоящее измерение либо решение аналитика о ручной проверке
геометрии. Тестировщик не меняет классы и не подменяет высоту на произвольную
константу. Ссылки «Тест» пусты, ручная C6 не выполнена.

## Общие файлы и передача ведущему

`frontend/src/screens/v2/test-support/fbsOrdersDom.tsx` — общая фикстура трёх
DOM-наборов, без своих test cases. Её следует сохранить с первым контрактом
(WMS-716), чтобы следующие отдельные коммиты WMS-717/WMS-719 могли её использовать.
Этот файл не проверяет геометрию и не подменяет операцию списка заглушкой.

Данный отчёт: `docs/reviews/WMS-716-720-tests-before-code-2026-10-09.md`.
В документах требований изменены только «Тест», проверено программным сравнением
с исходной версией. «Вердикт», «Заключение», классы и весь остальной текст сохранены.
Продуктовый diff пуст; AGENTS.md/CLAUDE.md и канонический бэклог не менялись.
Git commit, push, browser/e2e, ревью, приёмка и CI не выполнялись.

Адресный запуск контрактов фронта:

```sh
cd frontend
npx vitest run src/screens/v2/FfFbsOrdersScreen.wms716.dom.test.tsx src/screens/v2/FfFbsOrdersScreen.wms717.dom.test.tsx src/screens/v2/FfFbsOrdersScreen.wms719.dom.test.tsx --maxWorkers=1 --minWorkers=1
```

Адресный запуск контрактов бэка:

```sh
cd backend
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q tests/test_wms716_fbs_counts.py tests/test_wms719_fbs_size_search.py -p no:cacheprovider --tb=short
```
