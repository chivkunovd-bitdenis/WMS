# WMS Feature Gate Protocol

Этот документ обязателен для любой WMS-задачи: поток требований, баг, UI/rework,
backend-изменение, складской процесс, FBS/FBO/WB/MP, приемка, отгрузка,
упаковка, сортировка, каталог, остатки, доступы, печать, deploy/release-заявка
или любое изменение видимого поведения.

Не нужно сначала классифицировать задачу как "фича", "баг" или "UI-мелочь".
Любая задача сначала превращается в атомарные feature cards и проходит один и тот
же flow. Классификация не может быть способом обойти Product gate.

Единственное исключение: пользователь прямо пишет, что это срочный production
hotfix и нужно чинить сейчас. Тогда агент фиксирует
`EMERGENCY_BYPASS_USER_APPROVED`, делает минимальное исправление, а после
стабилизации возвращает задачу в этот gate. Emergency bypass не является
продуктовой приемкой.

## Главный запрет

Запрещено начинать разработку, пока по конкретной карточке нет явного product
OK до разработки.

Запрещено говорить "готово", "принято", "product approved", "browser QA passed"
или "release-ready", если соответствующий gate не был реально выполнен и
зафиксирован.

## Обязательная цепочка

Каждая задача проходит через атомарные feature cards. Каждая карточка проходит
строго в таком порядке:

1. BA Feature Cards.
2. Product Before Dev.
3. Atomic Dev.
4. Code Review.
5. Product Browser Review After Dev.
6. Integration Result.

Каждый пункт выполняет отдельный изолированный агент с отдельным заданием,
артефактом и verdict. Оркестратор только координирует, режет задачу на карточки,
запускает роли и сводит статусы. Оркестратор не подменяет собой BA, Product,
Developer, Code Review или Product Browser Review.

Переход к следующему шагу запрещен без явного результата предыдущего шага.

## Gate 1. BA Feature Cards

BA Agent получает исходную задачу пользователя и превращает ее в список
атомарных feature cards. Это не dev task list и не технический план. Это
бизнес-описание того, какую складскую работу меняем.

Обязательный файл итерации:

```text
docs/feature-gates/<YYYY-MM-DD>-<short-slug>/FEATURE_CARDS_RU.md
```

Формат каждой карточки:

```yaml
feature_id:
title:
source_task:
business_goal:
warehouse_user:
real_world_scenario:
current_problem:
target_process:
screen_or_flow:
primary_action:
secondary_actions:
required_visible_data:
explicitly_unnecessary_data:
success_state:
error_state:
empty_state:
roles_permissions:
tenant_seller_warehouse_scope:
external_dependencies:
business_assumptions:
open_questions:
ba_agent:
product_agent:
dev_agent:
code_review_agent:
product_browser_agent:
changed_files:
tests_run:
commit_or_patch_ref:
blocking_issues:
status: BA_READY | BA_REWORK | BA_BLOCKED
```

BA Agent обязан ответить:

- что именно пользователь имел в виду;
- зачем это нужно бизнесу;
- какую физическую складскую работу делает человек;
- где в интерфейсе это живет;
- что должно быть видно на этом шаге;
- что лишнее на этом шаге;
- какой результат пользователь видит при успехе;
- что происходит при ошибке и пустом состоянии;
- какие допущения приняты, если пользователь не проговорил детали.

Без `BA_READY` по конкретной карточке Product Before Dev не стартует.

## Gate 2. Product Before Dev

Product Agent до разработки работает по
[docs/WMS_PRODUCT_AGENT_RU.md](docs/WMS_PRODUCT_AGENT_RU.md).

Он получает одну `BA_READY` feature card и проверяет, будет ли предложенный
процесс реально удобен, понятен, минимален и пригоден для сотрудника склада.

Он обязан проверить:

- это похоже на реальный складской процесс;
- понятно, что делать дальше;
- основной сценарий выполняется минимальным числом кликов;
- экран не перегружен;
- нет лишних чипов, лейблов, бейджей;
- нет технического текста, подсказок для разработчиков и внутренних комментариев;
- нет дублирующих кнопок;
- нет лишних колонок;
- длинные SKU, штрихкоды, названия, статусы и комментарии не ломают строки и не
  перекрывают действия;
- изменение не ломает приемку, отгрузку, сборку, сканирование, упаковку,
  маркировку или учет остатков.

Выход:

- `PRODUCT_APPROVED_FOR_DEV` — dev может стартовать;
- `PRODUCT_REWORK_REQUIRED` — карточка возвращается в BA/Product;
- `PRODUCT_BLOCKED` — не хватает экрана, данных, доступа, fixture или решения.

Без `PRODUCT_APPROVED_FOR_DEV` разработка запрещена.

## Gate 3. Atomic Dev

Dev Agent реализует ровно одну утвержденную карточку.

Правила:

- один Dev Agent = одна feature card;
- не брать соседние карточки;
- не делать незапрошенный redesign;
- не добавлять технический текст в UI;
- не плодить чипы, лейблы, кнопки, фильтры и колонки;
- не менять фронт в backend-задаче без явного product approval;
- сохранять существующие WMS-паттерны;
- не трогать секреты, токены, Railway variables и кабинеты ключей без отдельного
  явного запроса пользователя;
- по завершении перечислить измененные файлы и пользовательские сценарии.

Выход:

- `DEV_DONE`;
- `DEV_BLOCKED`.

## Gate 4. Code Review

Code Review Agent проверяет код, границы, тесты и регрессии. Он не принимает
продукт и не заменяет Product Browser Review.

Он ищет:

- регрессии;
- сломанные сценарии;
- плохие состояния ошибок;
- лишнюю связанность;
- нарушение существующих паттернов;
- отсутствие нужных тестов;
- риск конфликтов с другими фичами;
- UI-мусор, если он попал в код.

Выход:

- `CODE_REVIEW_PASSED`;
- `CODE_REVIEW_FAILED`;
- `CODE_REVIEW_BLOCKED`.

Если review failed, карточка возвращается в dev. После rework снова нужны Code
Review и Product Browser Review.

## Gate 5. Product Browser Review After Dev

Product Agent после разработки снова работает по
[docs/WMS_PRODUCT_AGENT_RU.md](docs/WMS_PRODUCT_AGENT_RU.md), но теперь обязан
открыть реальный живой браузер с видимой вкладкой и руками пройти сценарий в UI.

Не засчитывается:

- Playwright;
- headless browser;
- API/curl/методы;
- unit/integration tests;
- скриншоты без живого прохода;
- чтение кода;
- рассказ разработчика;
- эмуляция вместо реального клика в интерфейсе.

Если нет доступа к реальному браузеру, данным, стенду, авторизации или безопасной
fixture, verdict только `PRODUCT_BROWSER_BLOCKED`.

Выход:

- `PRODUCT_BROWSER_APPROVED`;
- `PRODUCT_REWORK_REQUIRED`;
- `PRODUCT_BROWSER_BLOCKED`.

Без `PRODUCT_BROWSER_APPROVED` карточка не закрыта.

## Rework

Любое изменение после Product verdict аннулирует старый product verdict для
затронутой карточки или зоны экрана. Rework повторяет цепочку:

```text
BA уточнение -> Product Before Dev -> Dev -> Code Review -> Product Browser Review
```

Нельзя "чуть поправить" и засчитать старый Product Browser Review.

## Параллельность

Параллельно можно запускать только независимые карточки, у которых не
пересекаются:

- экран;
- компонент;
- API route;
- сервис;
- модель данных;
- таблица БД;
- тестовый сценарий;
- печатный документ;
- складской процесс.

Если зоны пересекаются, оркестратор обязан назначить порядок. Два Dev Agent не
имеют права одновременно менять один экран, сервис, таблицу или компонент.

## Финальный integration review

После per-card Product Browser Review по всем карточкам запускается общий review.
Он проверяет все изменения вместе:

- нет UX-разнобоя между экранами;
- нет разных названий для одной сущности;
- нет конфликтующих кнопок;
- нет повторяющихся действий;
- не стало слишком много экранов;
- не появились лишние колонки, чипы, лейблы;
- не сломан общий FBS/FBO/MP/fulfillment процесс;
- нет ощущения, что каждую карточку делал отдельный человек без общей системы.

Если общий reviewer находит проблему, конкретные карточки возвращаются на
доработку.

## Финальный browser regression

После общего reviewer обязателен общий браузерный прогон затронутых процессов:

- открыть ключевые экраны;
- пройти основные сценарии;
- проверить переходы между экранами;
- проверить, что фичи не мешают друг другу;
- проверить, что интерфейс остался простым;
- проверить, что сотруднику fulfillment понятно, что делать дальше;
- проверить отсутствие технических надписей, лишних чипов, лишних кнопок и
  лишних колонок.

Без финального browser regression итерация не завершена.

## PR / CI Product Gate

PR должен содержать `## Product gate` с перечислением feature cards и verdict по
каждой роли. CI проверяет наличие этого блока, но CI не доказывает качество
product review: он только не дает молча забыть артефакт.

Обязательные поля PR:

```yaml
feature_cards_path:
feature_ids:
ba_agents:
product_agents_before_dev:
dev_agents:
code_review_agents:
product_browser_agents_after_dev:
real_browser_evidence_paths:
verdicts:
emergency_bypass:
```

## Обязательный отчет

Финальный ответ агента по задаче должен разделять:

- local;
- committed;
- pushed;
- deployed;
- browser-tested;
- remaining risks.

И показывать счетчики:

| Метрика | Количество |
| --- | ---: |
| total_cards | |
| ba_ready | |
| product_approved_for_dev | |
| product_rework_required | |
| product_blocked | |
| dev_done | |
| code_review_passed | |
| product_browser_approved | |
| product_browser_rework_required | |
| product_browser_blocked | |
| integrated | |
| final_regression_passed | |

## Definition Of Done

Карточка считается done только если:

- есть BA feature card;
- есть `BA_READY`;
- есть `PRODUCT_APPROVED_FOR_DEV`;
- есть `DEV_DONE`;
- есть `CODE_REVIEW_PASSED`;
- есть `PRODUCT_BROWSER_APPROVED`;
- изменения сохранены в Git отдельным commit;
- известен commit SHA.

Итерация считается done только если:

- все карточки done;
- общий integration review passed;
- общий browser regression passed;
- изменения закоммичены;
- известен итоговый commit SHA;
- если нужно другим людям или CI, ветка запушена;
- если нужен staging, он собран именно из итогового SHA;
- если нужен deploy, явно проверено, какой SHA развернут.

Если хотя бы один gate не пройден, статус должен быть честным: `blocked`,
`failed` или `partial`. Запрещено называть такую работу готовой.
