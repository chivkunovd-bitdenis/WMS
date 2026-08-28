# Product Browser Review After Dev — A-2 «Категория товара из предмета Wildberries»

## Граница проверки

Проверка выполнена отдельным Product Browser Review Agent после
`CODE_REVIEW_PASSED`. Production- и test-код не изменялись. Использовался живой
локальный WMS в Codex In-app Browser, а не headless-браузер и не отдельный
Playwright-прогон.

A-2 утверждена как backend-подготовка данных для будущих потребителей: в её
scope нет нового поля, фильтра или иного элемента существующего экрана. Поэтому
проверка разделена на две честные части:

1. живой проход по видимому каталогу, чтобы обнаружить UI-регрессию;
2. вспомогательное браузерное evidence наличия нового API-маршрута, которое не
   подменяет продуктовую проверку видимого поведения.

## Живой проход

Окружение:

- UI: `http://127.0.0.1:5274/app/ff/products`;
- API documentation: `http://127.0.0.1:18280/docs`;
- роль: локальный `fulfillment_admin`;
- пользователь: локальная безопасная fixture A-3 baseline;
- селлер в единственной строке каталога: `Селлер baseline`;
- склад: на этом экране не выбирается, категория принадлежит Product.

Выполненные действия и наблюдения:

1. Через левое меню нажата ссылка `Каталог`; открыт маршрут
   `/app/ff/products`.
2. На вкладке `Товары` видны прежние действия `Загрузить Excel` и
   `Создать товар`, поиск, фильтры `Селлер`, `Маркетплейс`, `Категория` и
   прежняя таблица. Новых колонок, кнопок, чипов и технического текста от A-2
   не появилось.
3. В таблице виден товар `Футболка baseline` с SKU
   `A3-SKU-1787904738`, селлером и прежними блоками остатков/действий. Текст не
   перекрывает действия, горизонтальная структура строки сохранена.
4. В поиск введено `НЕСУЩЕСТВУЮЩИЙ-SKU`; экран показал проверяемое пустое
   состояние `Найдено: 0 из 1` и `Ничего не найдено.` без ошибки и без
   исчезновения заголовков таблицы.
5. Поиск очищен; нажата вкладка `Короба и грузоместа`, где сохранилось штатное
   пустое состояние `Коробов и грузомест пока нет`, затем выполнен возврат на
   `Товары`.
6. После reload снова видны `Найдено: 1 из 1` и исходный SKU. В browser console
   ошибок нет.
7. В живом Swagger UI открыт раздел `products`; в нём виден отдельный
   статический `GET /products/categories` между `POST /products` и другими
   статическими product-маршрутами. Это подтверждает наблюдаемость маршрута в
   запущенном приложении, но не доказывает его бизнес-результат в UI.

## Что нельзя принять браузером

Ни один пользовательский экран в утверждённом scope A-2 не показывает
`Product.category` и не отображает результат `GET /products/categories` как
список, применённый к складской операции. На открытом каталоге есть ранее
существовавшая подпись/комбобокс `Категория`, но реализация A-2 его не меняла и
не связывала с новым контрактом; категория fixture `Футболки` не становится на
этом экране отдельным видимым значением товара.

Следовательно, в живом UI невозможно руками доказать утверждённые success,
empty, error и tenant/seller-scope состояния нового контракта. Авторизованный
ответ API, backend-тесты, Swagger и чтение кода являются техническим evidence,
но протокол прямо запрещает засчитывать API-only проверку как Product Browser
Review. Положительный browser verdict здесь был бы выдуманным.

Это не найденная регрессия продукта и не требование самовольно расширить A-2 на
чужой фронт. Блокер структурный: карточка объявлена backend-only, тогда как её
закрытие по текущему gate требует видимого пользовательского потребителя.
Приёмка будущего фильтра должна пройти в отдельной карточке карты склада или
раскладки после того, как этот экран начнёт читать новый контракт.

## Проверка запретной зоны

Diff относительно `7783a27c` не содержит изменений в:

- `frontend/src/screens/ff/warehouse-map/`;
- `frontend/src/screens/ff/sorting-objects/`;
- `frontend/src/ui-kit/`.

Результат read-only команды: `PROTECTED_DIRS_UNCHANGED`.

## Обязательный verdict

```yaml
feature_id: A-2
agent_name: a2_product_browser
isolated_agent: yes
review_stage: after_dev
professional_context:
  wms: yes
  logistics: yes
  fulfillment: yes
  marketplaces_wb: yes
real_browser_used: yes
browser_type: "Codex In-app Browser; живая отрисованная вкладка, ручные клики и ввод"
environment_url: "http://127.0.0.1:5274"
role: fulfillment_admin
tenant: "local baseline tenant; имя тенанта не выводится на проверенном экране"
seller: "Селлер baseline"
warehouse: "not applicable on Product catalog"
screen_urls:
  - "http://127.0.0.1:5274/app/ff/products"
  - "http://127.0.0.1:18280/docs#/products/get_product_categories_products_categories_get"
actions_clicked:
  - "левое меню: Каталог"
  - "комбобокс: Категория"
  - "вкладка: Короба и грузоместа"
  - "вкладка: Товары"
  - "Swagger operation: GET /products/categories"
inputs_or_scans:
  - "поиск: НЕСУЩЕСТВУЮЩИЙ-SKU"
success_seen: "Каталог загрузил единственную строку A3-SKU-1787904738; после очистки поиска и reload строка восстановилась; новый route виден в живом Swagger UI. Само значение Product.category в UI не показано."
error_seen: "Ошибок browser console нет; error-state нового category API в пользовательском UI отсутствует и потому не проверяем."
empty_state_seen: "Видимое пустое состояние поиска каталога и пустое состояние вкладки коробов проверены; [] нового category API в пользовательском UI не отображается."
reload_readback_seen: "После reload видны Найдено: 1 из 1 и A3-SKU-1787904738."
element_verdicts:
  rows: "Единственная товарная строка читаема; видимой category-ячейки A-2 нет."
  columns: "Существующий состав колонок сохранён; новая колонка не добавлена."
  buttons: "Загрузить Excel, Создать товар и действия строки сохранены; дублей от A-2 нет."
  labels: "Складские подписи штатные; технический текст A-2 не появился."
  fields: "Поиск и прежние комбобоксы работают; Product.category как видимое поле отсутствует."
  filters: "Существующие Селлер, Маркетплейс и Категория визуально сохранены; связь нового API со screen flow в scope A-2 отсутствует."
  chips: "Новых chips нет."
  statuses: "Новых статусов нет."
  dialogs: "A-2 не добавляет dialogs; не применимо."
  text_fit: "На проверенной fixture текст не перекрывает кнопки и соседние значения."
warehouse_usability_verdict: "Видимый каталог не получил регрессии, но складской пользователь пока не может увидеть или применить новый устойчивый атрибут категории в утверждённом scope."
demo_risk: "high for demonstrating A-2 as a product outcome: клиенту можно показать только неизменившийся каталог и технический API route, но не работу категории в складском интерфейсе."
verdict: PRODUCT_BROWSER_BLOCKED
evidence_paths:
  - "docs/feature-gates/2026-08-28-product-category-wb-subject/evidence/live-catalog.jpg"
  - "docs/feature-gates/2026-08-28-product-category-wb-subject/evidence/catalog-empty-search.jpg"
  - "docs/feature-gates/2026-08-28-product-category-wb-subject/evidence/swagger-products-categories-route.jpg"
  - "docs/feature-gates/2026-08-28-product-category-wb-subject/CODE_REVIEW_RU.md"
blocking_issues:
  - "В scope A-2 нет живого UI-потребителя Product.category или GET /products/categories; API/Swagger/tests не могут заменить обязательную продуктовую browser-проверку видимого результата."
```

`PRODUCT_BROWSER_BLOCKED`
