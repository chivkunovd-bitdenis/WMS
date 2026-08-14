# Handoff в новый чат: WMS product/UX gate, строгий режим

Дата handoff: 2026-08-13.

Рабочий Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Ветка: `iteration/wms-product-ux-features-20260812`.

Application deploy SHA после завершения strict gate и stage verification:
`595bf93404794ade562b7f9fc4d6c1bdc09267c6`.

Примечание: итоговые evidence-документы stage могут быть сохранены отдельным
docs-only commit после деплоя. Это не меняет application deploy SHA, из которого
собраны backend/frontend на Railway.

Исторический статус на момент первоначального handoff: **не готов**, **не
прошёл final integration review**, **не проходил финальный общий browser
regression после возвратов**, **на staging не лить**.

Текущий статус после автономного strict rerun и stage verification 2026-08-14:
per-feature strict live Product gates закрыты, повторный Final Integration
Review прошёл, финальный live Product Browser Regression rerun прошёл, stage
развернут и проверен из итогового commit. Оперативный browser-regression
artifact:
`evidence/final-browser-regression-rerun-live-strict/FINAL_BROWSER_REGRESSION_RERUN_LIVE_STRICT_RU.md`
с verdict `FINAL_BROWSER_REGRESSION_PASSED`.

Stage proof artifact:
`evidence/stage-deploy-verification-595bf93/STAGE_DEPLOY_VERIFICATION_595BF93_RU.md`
с verdict `STAGE_DEPLOY_VERIFIED`.

Проверенный stage:

- application deploy SHA: `595bf93404794ade562b7f9fc4d6c1bdc09267c6`;
- `origin/staging` -> этот SHA;
- Railway backend `WMS` deployment
  `321617c0-5727-445d-a426-c6b2ee952b3c` -> `SUCCESS`;
- Railway frontend `web` deployment
  `063166b4-a27e-4071-a558-b0aeeaeecd24` -> `SUCCESS`;
- public web smoke passed:
  `https://web-production-9e7c1.up.railway.app/`;
- public API smoke passed:
  `https://wms-production-780c.up.railway.app/health`;
- live Chromium `headless=false` browser smoke passed at `1440x900`, screenshot
  and JSON saved under `evidence/stage-deploy-verification-595bf93/`.

## 1. Что произошло и почему этот handoff нужен

В текущем чате была запущена большая WMS-итерация по пулу фич. Формально по матрице многие фичи получили `BROWSER_PRODUCT_QA_PASSED`, но затем общий Final Integration Reviewer вернул релиз на доработку. Главная причина: ранние product/browser gates были слишком мягко интерпретированы и местами засчитывали артефакты, код или e2e вместо полноценного живого продуктового прокликивания в браузере.

Это нарушило изначальный пользовательский протокол. Новый чат обязан продолжить строго по протоколу, без самовольной разработки оркестратором.

Важно: в конце старого чата оркестратор начал сам править UI/API упаковки. Пользователь это запретил. Эти самовольные правки по упаковке были убраны из diff. Новый чат не должен продолжать разработку руками оркестратора. Любая правка должна идти через отдельного Atomic Dev Agent.

## 2. Жёсткие правила нового чата

1. Оркестратор не разрабатывает фичи сам.
2. Одна фича или одна возвращённая на доработку зона = один изолированный проход.
3. Для каждой фичи/доработки нужны отдельные агенты:
   - Business Analyst Agent;
   - Product / UX Agent;
   - Atomic Dev Agent;
   - Code Review Agent;
   - Browser Product QA Agent.
4. Если фича возвращена после review, она снова проходит весь цикл: BA/UX clarification -> Product/UX OK -> Atomic Dev -> Code Review -> live Browser Product QA.
5. Product approval до разработки не заменяет browser QA после разработки.
6. Browser Product QA считается пройденным только если отдельный agent реально открыл систему в живом браузере, кликал, вводил/сканировал/выбирал и прошёл складской сценарий глазами сотрудника fulfillment.
7. Зелёные unit/API/build/e2e тесты не являются product acceptance.
8. Запрещено ставить `passed`, если отдельный Product Browser Agent не дал явный `PRODUCT_BROWSER_APPROVED` / `BROWSER_PRODUCT_QA_PASSED` по конкретной фиче.
9. Запрещено лить на staging, пока не пройдены:
   - все per-feature gates;
   - повторный Final Integration Review;
   - общий финальный browser regression по всем связанным процессам.
10. Нельзя трогать production. Staging только Railway и только после final gates.
11. Нельзя трогать секреты, токены, Railway variables, secret panels, кабинеты ключей.
12. Нельзя использовать `git add .`; staged set должен быть scoped.
13. Нельзя объявлять “готово” без commit SHA и без проверки, что staging собран именно из этого SHA, если deploy нужен.

## 3. Кто такой Product / UX Agent и что он обязан доказать

Product / UX Agent в этой итерации — не формальный ревьюер текста, макета, теста
или карточки. Это роль профессионального product owner с сильной экспертизой в
логистике, складских операциях, WMS, fulfillment, FBS/FBO/MP-процессах и
маркетплейсах. Он смотрит на систему как человек, который отвечает за реальную
скорость, понятность, безопасность и экономику работы склада.

Product / UX Agent обязан по каждой фиче и каждому затронутому процессу открыть
живую систему в браузере, пройти сценарий руками, протыкать и прокликать экран
как сотрудник склада: выбрать, ввести, отсканировать, нажать, увидеть успех,
увидеть ошибку, проверить пустое состояние, reload/read-back и переходы. Документ,
скриншот, e2e, API-тест, code review или рассказ другого агента не заменяют его
собственный живой проход.

Это правило относится к любому Product / UX verdict, включая pre-dev approval
по BA/UX spec. `PRODUCT_APPROVED_FOR_DEV` без собственного live browser
click-through недействителен так же, как финальный browser pass без браузера.
Артефакт Product / UX Agent обязан явно указать `browser_used: yes/no`, URL/ports,
роли, маршруты, клики/ввод/сканы и evidence paths. Если этих полей и фактического
прохода нет, orchestrator обязан считать verdict invalid и перезапустить Product
Agent, а не отдавать фичу в разработку.

Его задача — жёстко разобрать не только UI, но и сам складской процесс. Если
экран, маршрут, кнопка, поле, колонка, чип, надпись, статус, подсказка, печатный
артефакт или шаг процесса не помогает сотруднику выполнить конкретную работу,
замедляет его, перегружает интерфейс, создаёт риск ошибки, дублирует другое
действие или выглядит как технический мусор, Product / UX Agent обязан поставить
rework, а не искать способ зачесть фичу.

На каждый визуальный элемент должно быть понятное продуктово-складское
обоснование:

- какую работу сотрудник делает именно в этот момент;
- почему этот элемент нужен для этой работы;
- ускоряет ли он действие или хотя бы снижает риск ошибки;
- не заставляет ли он читать лишнее, думать о технических деталях или искать
  главное действие;
- нет ли более простого способа показать тот же смысл;
- не мешает ли элемент соседним действиям, сканированию, упаковке, отгрузке,
  маркировке, учёту остатков или работе на экране 1280 px.

Норма качества: система должна быть уникально оптимальной, простой, понятной и
функциональной для реального fulfillment/Wildberries/WMS-оператора. Если Product
/ UX Agent не может уверенно сказать, что обычный сотрудник склада выполнит
процесс без объяснений и без лишней когнитивной нагрузки, verdict только
`PRODUCT_REWORK_REQUIRED`.

Фича не закрывается без явного product verdict по живому проходу:

- `PRODUCT_BROWSER_APPROVED` / `BROWSER_PRODUCT_QA_PASSED` — только если Product
  / UX Agent сам прокликал процесс в браузере и зафиксировал, почему UI и процесс
  годятся для склада;
- `PRODUCT_REWORK_REQUIRED` — если процесс, UI или доказательства неполные;
- `PRODUCT_BROWSER_BLOCKED` — если живой проход технически невозможен.

Если verdict не положительный, фича возвращается на предыдущий круг
BA/Product/Dev/QA. Нельзя закрывать фичу по матрице, если этот живой product pass
не доказан отдельным артефактом.

## 4. Обязательная переаттестация старых `passed`

Новый чат не имеет права доверять прежним `BROWSER_PRODUCT_QA_PASSED`,
`PRODUCT_APPROVED_*` или `integration_pending` только потому, что они стоят в
matrix или карточке. Эти статусы были выставлены до уточнённого определения
Product / UX Agent и могли быть засчитаны поверхностно.

Перед продолжением release нужно по каждой активной фиче F01-F19, F22, F23
проверить evidence и ответить:

1. Есть ли отдельный Product / UX verdict по этой фиче.
2. Открывал ли Product / UX Agent живую систему в браузере именно сам.
3. Был ли реально прокликан основной складской сценарий, включая ввод,
   сканирование, выбор, ошибки, пустое состояние, успех, reload/read-back и
   переходы там, где это применимо.
4. Есть ли экспертный разбор UI/процесса: каждый чип, колонка, надпись, кнопка,
   поле и шаг имеют складское обоснование, не тормозят сотрудника и не
   перегружают экран.
5. Не противоречит ли более поздний failed/blocked evidence более раннему
   passed.

Если хотя бы один пункт не доказан, фича получает статус
`STRICT_PRODUCT_RECERT_REQUIRED` и должна заново пройти Product / UX Agent pass
по живому браузеру. Если Product / UX Agent ставит `PRODUCT_REWORK_REQUIRED`,
фича возвращается на BA/UX или Atomic Dev по обычному циклу и не считается
закрытой.

Нельзя заменять эту переаттестацию:

- headed Playwright/e2e without product critique;
- API/unit/build checks;
- screenshots без описания пройденного процесса;
- code review;
- записью `passed` в matrix без независимого артефакта.

Абсолютное правило: отсутствие живого браузерного прохода самим Product / UX
Agent никогда не превращается в approval. Если браузер не поднялся, кончилось
место, сломалась тестовая среда, не хватает данных или агент смог прочитать
только старые evidence-файлы, verdict может быть только
`PRODUCT_BROWSER_BLOCKED` или `PRODUCT_REWORK_REQUIRED`, но не
`STRICT_PRODUCT_BROWSER_APPROVED`.

## 5. Точный первичный промпт пользователя для нового чата

Ниже нужно вставить в новый чат как стартовый протокол. Он сохранён как исходная пользовательская рамка работы.

````text
Ты оркестратор автономной мультиагентной WMS-итерации.

Цель: взять пул фичей/рефакторингов WMS и довести их до рабочего состояния без участия пользователя. Главное качество результата: реальный, простой, неперегруженный UI/UX для сотрудников fulfillment/Wildberries/FBS, проверенный руками в браузере.

Работай автономно. Не задавай пользователю вопросов, если можно принять разумное профессиональное решение. Если данных не хватает, фиксируй допущение и продолжай. Останавливаться можно только при реальной технической невозможности продолжать.

## 0. Обязательный старт

Сначала обязательно:

1. Найди настоящий Git-root через `git rev-parse --show-toplevel`.
2. Прочитай `AGENTS.md`.
3. Проверь `git status`.
4. Не работай в `/Users/deniscivkunov/Desktop/WMS`, если это не Git-репозиторий.
5. Проверь реальные checkout-кандидаты:
   - `/Users/deniscivkunov/Desktop/WMS `
   - `/Users/deniscivkunov/Projects/WMS`
6. Создай отдельную ветку для итерации.
7. Зафиксируй базовый commit SHA до начала работ.
8. Не трогай секреты, ключи, кабинеты токенов и внешние secret-панели.
9. Не объявляй “готово”, если нет итогового commit SHA.

## 1. Главный принцип работы

Каждая фича проходит изолированно.

Нельзя смешивать несколько фичей в одну разработческую кашу. Для каждой фичи должен быть отдельный атомарный проход:

1. Feature Intake
2. Business Analysis
3. UX/Product Design
4. WB/Fulfillment Product Review
5. Atomic Development
6. Code Review
7. Per-feature Browser Product QA
8. Feature Integration Result

Один dev-агент реализует одну фичу. Если фича слишком большая, оркестратор обязан сначала разрезать ее на атомарные подфичи и прогнать каждую отдельно.

## 2. Роли агентов

Используй мультиагентный режим. Оркестратор управляет всей волной, но не должен сам тащить все роли, если доступны subagents.

Для каждой фичи запускай изолированные роли:

### Business Analyst Agent

Задача: превратить сырое описание фичи в понятный складской сценарий.

Он обязан описать:

- кто пользователь;
- какую работу он делает на складе;
- какой экран открывает;
- что должен увидеть;
- какое основное действие выполняет;
- какой результат получает;
- какие данные обязательны;
- какие данные лишние;
- какие состояния нужны: пусто, ошибка, успех.

Если постановка неполная, агент не спрашивает пользователя, а принимает лучшее разумное допущение и фиксирует его.

### UX/Product Design Agent

Задача: спроектировать экран или изменение экрана без визуального мусора.

Он обязан проверить:

- нет ли лишних чипов, лейблов, бейджей;
- нет ли технических подсказок для разработчиков;
- нет ли дублирующих кнопок;
- нет ли лишних столбцов;
- видны ли нужные столбцы;
- понятно ли главное действие;
- не перегружен ли экран;
- можно ли выполнить процесс с минимальным числом кликов;
- не ломает ли изменение существующий UX WMS.

### WB/Fulfillment Product Agent

Задача: проверить фичу глазами профессионального product owner, логиста и складского эксперта по Wildberries, FBS, FBO/MP, fulfillment, WMS, отгрузкам, упаковке, маркировке и учёту остатков.

Это не ревью текста или автотеста. Product Agent обязан открыть живую систему в браузере и сам пройти процесс руками: кликать, выбирать, вводить, сканировать, проверять успех, ошибку, пустое состояние, reload/read-back и переходы. Он обязан жёстко разобрать сам процесс и каждый визуальный элемент: чип, колонку, кнопку, поле, надпись, статус, подсказку, печатный артефакт и шаг сценария.

На каждый визуальный элемент должен быть ответ: какую конкретную складскую работу он помогает выполнить, ускоряет ли он сотрудника, снижает ли риск ошибки, не добавляет ли лишнее чтение/мышление/клики, не перегружает ли экран и не мешает ли соседним действиям. Если обоснования нет, элемент считается лишним шумом и фича возвращается на rework.

Он обязан ответить:

- это похоже на реальный складской процесс?
- сотруднику fulfillment понятно, что делать дальше?
- не добавляет ли фича лишнюю когнитивную нагрузку?
- не ломает ли процесс отгрузки, сборки, сканирования, упаковки или маркировки?
- нет ли лишних экранов, вкладок, кнопок, статусов?
- можно ли это дать обычному сотруднику склада без объяснений?
- доказан ли живой browser pass именно Product Agent, а не только e2e/API/code review?
- есть ли продуктово-складское обоснование у каждого чипа, поля, колонки, кнопки и надписи?

Если ответ нет, фича возвращается на Business Analysis/UX Design и не идет в разработку. Если такой живой product pass не проведён или evidence не доказывает его, фича не получает даже `PRODUCT_APPROVED_FOR_DEV`: она не идёт в разработку и не считается закрытой.

### Atomic Dev Agent

Задача: реализовать только одну утвержденную фичу.

Правила:

- один dev-агент = одна фича;
- не захватывать соседние фичи;
- не делать незапрошенный redesign;
- не менять глобальную архитектуру без необходимости;
- сохранять существующие WMS-паттерны;
- не добавлять технический текст в UI;
- не добавлять декоративный шум;
- не плодить чипы/лейблы/кнопки;
- после реализации дать точный список измененных файлов и сценариев.

### Code Review Agent

Задача: проверить код как профессиональный reviewer.

Он ищет:

- регрессии;
- сломанные сценарии;
- плохие состояния ошибок;
- лишнюю связанность;
- нарушение существующих паттернов;
- отсутствие нужных тестов;
- риск конфликтов с другими фичами.

Code review не заменяет browser QA.

### Per-feature Browser Product QA Agent

Это обязательный gate для каждой фичи.

Агент обязан открыть UI в браузере и руками пройти сценарий. API/unit-тесты не считаются заменой.

Он проверяет:

1. Реальный экран открывается.
2. Основной сценарий проходит руками.
3. Кнопки нажимаются.
4. Ввод/сканирование/выбор работают.
5. Успех виден пользователю.
6. Ошибка понятна пользователю.
7. Пустое состояние понятно.
8. UI не перегружен.
9. Нет технического мусора.
10. Нет лишних чипов/лейблов/столбцов.
11. Нет дублирующих кнопок.
12. Сотруднику fulfillment понятно следующее действие.

Если browser QA не пройден, фича возвращается в разработку. Фича без browser QA approval не может быть интегрирована как завершенная.

## 3. Изоляция фичей

Для каждой фичи веди отдельную карточку:

```md
id:
title:
status:
owner_dev_agent:
business_goal:
warehouse_user:
main_real_world_scenario:
screens_touched:
required_visible_data:
forbidden_ui_noise:
primary_actions:
secondary_actions:
empty_state:
error_state:
success_state:
business_assumptions:
ux_decision:
product_review_result:
dev_result:
code_review_result:
browser_qa_result:
changed_files:
tests_run:
commit_or_patch_ref:
blocking_issues:
Статусы:
draft
business_ready
ux_ready
product_rejected
ready_for_dev
dev_done
code_review_failed
code_review_passed
browser_qa_failed
browser_qa_passed
integrated
final_regression_passed
4. Параллельность
Можно запускать агентов параллельно только если их зоны файлов и экранов не конфликтуют.
Если две фичи трогают один экран, один сервис, одну таблицу или один компонент, оркестратор обязан:
сначала выявить конфликт;
назначить порядок;
не дать двум dev-агентам одновременно менять одну и ту же зону;
после обеих фичей провести объединенный review этого экрана.
5. Общий финальный reviewer
После того как отдельные фичи прошли свои изолированные browser QA, запусти общего Final Integration Reviewer.
Он обязан посмотреть все фичи вместе и проверить:
нет ли UX-разнобоя между экранами;
нет ли разных названий для одной сущности;
нет ли конфликтующих кнопок;
нет ли повторяющихся действий;
не стало ли экранов слишком много;
не появились ли лишние столбцы/чипы/лейблы;
не сломался ли общий процесс FBS/fulfillment;
не противоречат ли фичи друг другу;
нет ли ощущения “каждую фичу делал отдельный человек без общей системы”.
Если общий reviewer находит несоответствия, оркестратор возвращает конкретные фичи на доработку.
6. Общий финальный browser regression
После общего reviewer обязательно провести общий браузерный прогон всей системы в совокупности.
Нужно руками пройти связанные WMS-процессы, которые затронуты фичами:
открыть ключевые экраны;
пройти основные сценарии;
проверить переходы между экранами;
проверить, что новые фичи не мешают друг другу;
проверить, что интерфейс в целом остался простым;
проверить, что сотруднику fulfillment понятно, что делать дальше;
проверить, что нет технических надписей, лишних чипов, лишних кнопок и лишних столбцов.
Финальный browser regression является обязательным release gate.
Нельзя считать итерацию завершенной, если:
отдельная фича не прошла свой browser QA;
общий финальный browser regression не пройден;
изменения не закоммичены;
нет итогового commit SHA.
7. Тесты
Тесты нужны, но они вторичны относительно реального браузерного процесса.
Используй:
backend lint/typecheck/test там, где затронут backend;
frontend typecheck/build/unit там, где затронут frontend;
targeted Playwright/e2e там, где есть подходящие сценарии;
ручной browser QA обязательно.
Запрещено заменять живую браузерную проверку зелеными unit/API тестами.
8. Definition of Done
Итерация может считаться завершенной только если:
Все фичи прошли изолированный цикл.
У каждой фичи есть карточка.
У каждой фичи есть product approval.
У каждой фичи есть code review.
У каждой фичи есть per-feature browser QA approval.
Есть общий Final Integration Review.
Есть общий финальный browser regression.
Все изменения сохранены в Git.
Есть итоговый commit SHA.
Если требуется доступность другим людям, ветка запушена.
Если требуется deploy, отдельно проверено, что стенд собран именно из нужного SHA.
Финальный отчет должен явно разделять:
local
committed
pushed
deployed
browser-tested
remaining risks
9. Поведение при проблемах
Если агент блокируется:
не останавливай всю волну;
зафиксируй проблему;
сделай разумное допущение;
упрости фичу;
верни фичу на предыдущий этап;
или отложи только эту фичу, продолжив остальные.
Пользователя не спрашивать, если можно двигаться дальше.
10. Главный вопрос на каждом экране
Каждый reviewer и QA обязан смотреть на экран как сотрудник fulfillment:
“Передо мной конкретная складская работа. Я понимаю, что сейчас сделать, куда нажать, что отсканировать, где мой товар, где успех, где ошибка, и мне не мешает лишняя техническая муть?”
Если ответ не уверенное “да”, фича не проходит gate.
Начинай сразу: разложи пул фичей на атомарные карточки, запусти изолированные агентные проходы, затем интегрируй результаты, проведи общий review и общий browser regression. Не останавливайся на плане.
````

## 6. Дополнительные пользовательские правила, добавленные после старта

- Все изменения должны быть в отдельной ветке.
- После полного прохождения всех gates можно лить только на staging, не на production. Staging на Railway.
- Отдельный product agent должен решить по FBO/MP-отгрузке: оставлять текущий процесс отгрузки/упаковки или приводить почти к стандарту FBS. Он должен смотреть экраны, требования WB и код. Его verdict обязателен.
- Каждая фича и требование должны быть описаны BA artifact в формате: что, зачем, каким способом, почему.
- Product reviewer обязан следить не только за процессом, но и за размерами полей, колонок и кнопок: интерфейс должен быть аккуратным, лаконичным, не раздутым.
- Отдельный Product/Design review нужен по каталогу товаров селлера: убрать чиповый хаос, двойные кнопки, black strip/overflow, лишний `Лимит`, перегруз FBS-sync.
- Safe sync остатков WMS -> WB является отдельной фичей F22: нельзя занулять WB-остаток при ошибке, неясном расчёте или отсутствии безопасного FBS-пула.
- Строго запрещено продолжать разработку руками оркестратора. Разрабатывает только Atomic Dev Agent. Оркестратор управляет, фиксирует, проверяет, возвращает на доработку, но не правит код и UI сам.

## 7. Основные документы и ссылки

- Gate-протокол: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- BA artifact по всем фичам: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/ITERATION_BA_FEATURE_SPEC_RU.md`
- Feature cards / matrix: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`
- Strict product recert audit: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/STRICT_PRODUCT_RECERT_AUDIT_RU.md`
- Master product UX review: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/MASTER_PRODUCT_UX_REVIEW_RU.md`
- B06 packaging findings: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/B06_FINDINGS_RU.md`
- B06 process map: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/B06_INPUT_PROCESS_MAP_RU.md`
- B06 action ledger: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/B06_SCREEN_ACTION_LEDGER_RU.md`
- B06 execution checklist: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/B06_EXECUTION_CHECKLIST_RU.md`
- B06 handoff: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/B06_HANDOFF_RU.md`
- Evidence root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/`

## 8. Ссылки на все user stories / requirements

BA story anchors:

- F01 Приёмка без отдельного процесса упаковки: `ITERATION_BA_FEATURE_SPEC_RU.md:9`
- F02 Габариты товара прямо из приёмки: `ITERATION_BA_FEATURE_SPEC_RU.md:17`
- F03 Приёмка с расхождениями и добавлением любых товаров селлера: `ITERATION_BA_FEATURE_SPEC_RU.md:25`
- F04 Создание нового товара прямо из приёмки: `ITERATION_BA_FEATURE_SPEC_RU.md:33`
- F05 Единая карточка приёмки для ФФ и селлера: `ITERATION_BA_FEATURE_SPEC_RU.md:41`
- F06 Накладная из приёмки печатается по факту: `ITERATION_BA_FEATURE_SPEC_RU.md:49`
- F07 FBO/MP-отгрузка в понятной пошаговой логике: `ITERATION_BA_FEATURE_SPEC_RU.md:57`
- F08 Резервы и направления внутри товара: `ITERATION_BA_FEATURE_SPEC_RU.md:65`
- F09 Свободный остаток для FBO: `ITERATION_BA_FEATURE_SPEC_RU.md:73`
- F10 FBS-синхронизация берёт только FBS-пул: `ITERATION_BA_FEATURE_SPEC_RU.md:81`
- F22 Safe sync остатков WMS -> WB / ЛК селлера: `ITERATION_BA_FEATURE_SPEC_RU.md:89`
- F11 Упростить каталог ФФ: `ITERATION_BA_FEATURE_SPEC_RU.md:97`
- F12 Месячный snapshot остатков: `ITERATION_BA_FEATURE_SPEC_RU.md:105`
- F13 Точечный баг Виталика: `ITERATION_BA_FEATURE_SPEC_RU.md:113`
- F14 Сотрудники селлера и ФФ: `ITERATION_BA_FEATURE_SPEC_RU.md:121`
- F15 Удаление только черновиков: `ITERATION_BA_FEATURE_SPEC_RU.md:129`
- F16 Нормально назвать nmID: `ITERATION_BA_FEATURE_SPEC_RU.md:137`
- F17 Единый печатный документ: накладная + ТЗ: `ITERATION_BA_FEATURE_SPEC_RU.md:145`
- F18 Возвраты как вариант приёмки: `ITERATION_BA_FEATURE_SPEC_RU.md:153`
- F19 Возврат со сканированием и автопечатью ШК: `ITERATION_BA_FEATURE_SPEC_RU.md:161`
- F20 Счета клиентам: `ITERATION_BA_FEATURE_SPEC_RU.md:169` - out of scope.
- F21 Seller Focus Pro / лендинг WMS: `ITERATION_BA_FEATURE_SPEC_RU.md:177` - blocked missing repo/target.
- F23 Каталог товаров селлера cleanup: см. `ITERATION_FEATURE_CARDS_RU.md:282` и evidence `f23-*`.

Feature card anchors:

- Matrix: `ITERATION_FEATURE_CARDS_RU.md:9`
- F01: `ITERATION_FEATURE_CARDS_RU.md:41`
- F02: `ITERATION_FEATURE_CARDS_RU.md:55`
- F03: `ITERATION_FEATURE_CARDS_RU.md:73`
- F04: `ITERATION_FEATURE_CARDS_RU.md:91`
- F05: `ITERATION_FEATURE_CARDS_RU.md:104`
- F06: `ITERATION_FEATURE_CARDS_RU.md:119`
- F07: `ITERATION_FEATURE_CARDS_RU.md:130`
- F08: `ITERATION_FEATURE_CARDS_RU.md:141`
- F09: `ITERATION_FEATURE_CARDS_RU.md:154`
- F10: `ITERATION_FEATURE_CARDS_RU.md:168`
- F11: `ITERATION_FEATURE_CARDS_RU.md:181`
- F12: `ITERATION_FEATURE_CARDS_RU.md:188`
- F13: `ITERATION_FEATURE_CARDS_RU.md:195`
- F14: `ITERATION_FEATURE_CARDS_RU.md:203`
- F15: `ITERATION_FEATURE_CARDS_RU.md:215`
- F16: `ITERATION_FEATURE_CARDS_RU.md:221`
- F17: `ITERATION_FEATURE_CARDS_RU.md:228`
- F18: `ITERATION_FEATURE_CARDS_RU.md:235`
- F19: `ITERATION_FEATURE_CARDS_RU.md:245`
- F22: `ITERATION_FEATURE_CARDS_RU.md:257`
- F23: `ITERATION_FEATURE_CARDS_RU.md:282`
- F20: `ITERATION_FEATURE_CARDS_RU.md:307`
- F21: `ITERATION_FEATURE_CARDS_RU.md:312`

## 9. Все фичи текущего захода

Активные release-фичи: 21.

- F01 Приёмка без отдельного процесса упаковки.
- F02 Габариты товара прямо из приёмки.
- F03 Приёмка с расхождениями и добавлением любых товаров селлера.
- F04 Создание нового товара прямо из приёмки.
- F05 Единая карточка приёмки для ФФ и селлера.
- F06 Накладная из приёмки печатается по факту.
- F07 FBO/MP-отгрузка по шагам FBS-like.
- F08 Резервы/направления внутри товара.
- F09 Свободный остаток для FBO.
- F10 FBS-синхронизация берёт только FBS-пул.
- F11 Каталог ФФ упростить.
- F12 Месячный snapshot остатков.
- F13 Точечный баг Виталика.
- F14 Сотрудники селлера и ФФ.
- F15 Удаление только черновиков.
- F16 nmID нормально назвать.
- F17 Единый документ печати: накладная + ТЗ.
- F18 Возвраты как вариант приёмки.
- F19 Возврат со сканированием и автопечатью ШК.
- F22 Safe sync остатков WMS -> WB / ЛК селлера.
- F23 Каталог товаров селлера cleanup.

Не входят в release:

- F20 Счета клиентам: out of scope by user.
- F21 Seller Focus Pro / лендинг WMS: blocked, потому что в текущем WMS checkout нет repo/target `sellerfocus.pro`.

## 10. Текущий статус, который нельзя приукрашивать

По матрице многие фичи отмечены как `BROWSER_PRODUCT_QA_PASSED`, но после этого общий Final Integration Review вернул релиз. Поэтому нельзя считать итерацию готовой и нельзя деплоить.

Текущий итог:

- local: есть большой незакоммиченный/частично закоммиченный рабочий diff в ветке.
- committed: ветка ahead 41 от origin; текущий HEAD `ea08284021818233516a19422aee5f905c55d295`, но это не итоговый release SHA.
- pushed: ветка отстаёт/опережает origin как `ahead 41`; перед любым handoff/push проверять fresh `git status`.
- deployed: не деплоить; staging не подтверждён из итогового SHA.
- browser-tested: per-feature evidence есть по многим фичам, но final integration review failed; финальный общий regression не проведён после возвратов.
- remaining risks: P0 packaging/FBS process, P1 navigation/permissions discoverability, F19 artifact/status mismatch, incomplete master review blocks.

## 11. Final Integration Review result

Final Integration Reviewer вернул `FINAL_INTEGRATION_REVIEW_FAILED`.

Нужно считать это обязательным release blocker.

### P0: упаковочный процесс остаётся продуктово заблокированным

Вернуть на доработку F07, F17, F19.

Причины из `B06_FINDINGS_RU.md`:

- B06-F01: очередь не позволяет выбрать физически правильное задание.
- B06-F02: create автоматически выбирает все товары места и может смешать разных seller.
- B06-F03: сохранённое seller-ТЗ не доставлено на рабочее место упаковщика.
- B06-F04: нет scanner/unit-flow; кнопка `Упаковать` проводит весь остаток строки.
- B06-F05: quantity validation молча floor-ит дроби и плохо возвращает к ошибке.
- B06-F06: на 1280 px нельзя одним взглядом прочитать identity товара и действие.
- B06-F07: done/cancelled task исчезает после reload, нет доступной истории.
- B06-F08: marking queue показывает pool0, но не даёт recovery/next step.
- B06-F09: CTA lifecycle конкурирует; `Завершить` и массовое подтверждение визуально опасны.

Stop-gate из B06: перед массовым пилотом обязательны F01-F07 B06; F08-F09 обязательны до ЧЗ/плохо обученных упаковщиков.

### P1: F19 status mismatch

В matrix F19 указана как `BROWSER_PRODUCT_QA_PASSED`, но подробная карточка F19 всё ещё говорит `browser_qa_in_progress`. Есть файл `evidence/f19-browser-product-qa-final/QA_RESULT_RU.md`, но новый чат должен не просто “поправить строку”, а проверить evidence и синхронизировать карточку отдельным gate-действием.

### P1: F12/F14 navigation/permissions discoverability

Final reviewer нашёл конфликт: routes для FBS/packaging/inventory могут быть разрешены сотрудникам, но пункты меню скрыты админскими условиями. Вернуть F12/F14 на isolated rework cycle. Нельзя чинить это руками оркестратора.

Проверить:

- `frontend/src/layouts/AuthedAppLayout.tsx`
- `frontend/src/App.tsx`
- `frontend/tests-e2e/ff-staff-users.spec.ts`
- `backend/tests/test_staff_users.py`

### P1: Master review incomplete

`MASTER_PRODUCT_UX_REVIEW_RU.md` остаётся `IN_PROGRESS`, `READY_FOR_HANDOFF: NO`. B06 был полезен и дал stop-gates; B07-B10 могут быть `NOT_REVIEWED`. Новый чат должен читать документ периодически и подхватывать только полностью завершённые блоки, не смешивая incomplete findings с текущим release без отдельного intake.

## 12. Что конкретно делать новому чату

Новый чат должен:

1. Выполнить обязательный старт: `git rev-parse --show-toplevel`, `AGENTS.md`, `git status`.
2. Прочитать `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
3. Прочитать этот handoff.
4. Прочитать `ITERATION_BA_FEATURE_SPEC_RU.md`, `ITERATION_FEATURE_CARDS_RU.md`, `STRICT_PRODUCT_RECERT_AUDIT_RU.md`, `B06_FINDINGS_RU.md`, `MASTER_PRODUCT_UX_REVIEW_RU.md`.
5. Не кодить руками.
6. Создать отдельные rework cards для:
   - R01 Packaging/FBO/FBS operator process rework covering returned F07/F17/F19 blockers from B06.
   - R02 Staff navigation/permissions discoverability for F12/F14.
   - R03 F19 gate evidence/status reconciliation.
7. Для R01 сначала запустить BA Agent, потом live-browser Product/UX Agent. Product/UX должен открыть текущий UI в браузере, прокликать процесс, затем дать точный screen/process spec, включая размеры колонок/полей/кнопок. Только после `PRODUCT_APPROVED_FOR_DEV` с доказанным `browser_used: yes` запускать Atomic Dev Agent.
8. Для R02 аналогично: BA -> live-browser Product/UX -> Atomic Dev -> Code Review -> live Browser Product QA.
9. Для R03 сначала проверить evidence; если это только документный рассинхрон, всё равно зафиксировать isolated reviewer verdict; если evidence не доказывает live browser clicking, вернуть F19 на Browser Product QA.
10. После rework и per-feature live QA запустить новый Final Integration Reviewer.
11. Только если Final Integration Review passed, запустить общий final browser regression.
12. Только после final browser regression passed сделать scoped commit, получить итоговый SHA, push branch if needed, потом staging deploy на Railway only.

## 13. R01 Packaging/FBO/FBS operator process rework: требования

Это главный P0.

Product/UX Agent должен утвердить до разработки:

- очередь заданий показывает `номер · seller · склад/ячейка · 1-2 SKU/ШК · готово/всего`;
- строка очереди keyboard-accessible;
- create из ячейки стартует без auto-select;
- каждая строка create показывает seller;
- create summary показывает `N SKU / M единиц / K seller`;
- mixed-seller task блокируется или требует явно утверждённый product-confirmation; если такого контракта нет, блокировать;
- create/task panel показывают ТЗ, seller, склад, ячейку;
- scanner-first: autofocus на ШК товара;
- каждый валидный повторный scan даёт ровно `+1`;
- unknown/overage/zero product scan блокируется понятной ошибкой;
- ручной fallback `+N`;
- по возможности `Отменить последнее`; если слишком рискованно, BA/Product должны явно зафиксировать альтернативный безопасный recovery;
- qty input принимает только целое `>=1`, без silent floor;
- error у конкретной строки и focus на проблему;
- 1280 px layout: SKU/ШК, короткое имя, место, готово/осталось, главный CTA читаются без horizontal memory join;
- `Завершить` доступно только когда `осталось = 0`;
- массовое подтверждение показывает точное количество и последствия;
- done/cancelled доступны после reload через фильтры/историю/стабильную ссылку;
- marking pool0 показывает human next step: `Нет КМ — запросить у seller/ответственного`;
- внутренний `__SORTING__` не показывается пользователю, должно быть `Сортировка`.

После dev:

- Code Review Agent проверяет регрессии stock movement, double click, FBS integration, marking, history, no mixed seller.
- Browser Product QA Agent обязан открыть браузер и реально пройти сценарий mixed sellers + packaging:
  - создать/подготовить товары разных sellers в одной ячейке;
  - открыть упаковку;
  - убедиться, что create не выбрал всё автоматически;
  - выбрать только правильного seller;
  - пройти scan `+1`;
  - проверить unknown/overage;
  - завершить;
  - reload;
  - открыть done/history;
  - проверить, что другой seller stock не затронут;
  - проверить, что UI не раздут, без лишних чипов/кнопок/технического текста.

## 14. R02 F12/F14 navigation/permissions discoverability: требования

Проблема: backend/routes и меню должны совпадать для staff permissions.

BA/Product должны решить, что именно видит сотрудник:

- shipments/packaging staff должен видеть нужные пункты `Отгрузки`, `FBS`, `Упаковка`, если route разрешён;
- inventory/cells staff должен видеть `Каталог и ячейки` и `Инвентаризация`, если route разрешён;
- reception staff не видит лишнего;
- settings staff не видит складских разделов;
- меню не должно быть перегружено и не должно показывать запрещённые разделы.

После dev:

- Code Review Agent проверяет `AuthedAppLayout.tsx`, `App.tsx`, `ffPermissions`, backend deps и staff tests.
- Browser Product QA Agent логинится разными staff roles и реально проверяет меню + direct routes.

## 15. R03 F19 evidence/status reconciliation

Проблема: matrix и card расходятся по Browser QA.

Новый чат должен:

1. Открыть:
   - `ITERATION_FEATURE_CARDS_RU.md:245`
   - `evidence/f19-browser-product-qa-final/QA_RESULT_RU.md`
   - `evidence/f19-browser-product-qa/QA_RESULT_RU.md`
2. Проверить, был ли реально живой browser click-through по возврату со сканом/autoprint.
3. Если да, синхронизировать карточку через isolated reviewer/documentation step.
4. Если нет, запустить отдельный Browser Product QA Agent на F19.

Нельзя просто заменить `browser_qa_in_progress` на `passed` без проверки evidence.

## 16. Evidence inventory для быстрого старта

Смотреть прежде всего:

- `evidence/f05-browser-product-qa-after-geometry/QA_RESULT_RU.md`
- `evidence/f08-browser-product-qa-final/F08_BROWSER_PRODUCT_QA_FINAL_RU.md`
- `evidence/f09-browser-product-qa/F09_BROWSER_PRODUCT_QA_RU.md`
- `evidence/f10-browser-product-qa-final/QA_RESULT_RU.md`
- `evidence/f14-browser-product-qa/F14_BROWSER_PRODUCT_QA_RU.md`
- `evidence/f18-browser-product-qa-final/QA_RESULT_RU.md`
- `evidence/f19-browser-product-qa-final/QA_RESULT_RU.md`
- `evidence/f22-browser-product-qa-after-read-model/F22_BROWSER_PRODUCT_QA_AFTER_READ_MODEL_RU.md`
- `evidence/f23-browser-product-qa/F23_BROWSER_PRODUCT_QA_RU.md`

Но помнить: Final Integration Review failed, поэтому evidence не даёт право на staging.

## 17. Git / рабочее дерево

На момент handoff ветка dirty. Нельзя делать `git add .`.

Известно:

- branch: `iteration/wms-product-ux-features-20260812`
- current HEAD: `ea08284021818233516a19422aee5f905c55d295`
- status: ahead 41 от origin
- есть много modified files и untracked evidence/db/test-results
- untracked DB files и `test-results/` нельзя случайно включать в commit

Перед любым commit:

1. `git status --short --branch`
2. `git diff --stat`
3. `git diff -- <scoped files>`
4. stage only exact files needed
5. commit only after all required gates

## 18. Запреты для нового чата

- Не продолжать этот старый чат как рабочий rollout.
- Не реанимировать старые agents.
- Не считать старые `passed` финальным release approval после failed final integration.
- Не деплоить staging, пока R01/R02/R03 и final gates не пройдены.
- Не править UI/код руками оркестратора.
- Не открывать secret panels.
- Не менять Railway variables.
- Не пушить/деплоить production.
- Не писать пользователю “готово”, пока нет итогового commit SHA и staging SHA verification.

## 19. Минимальный стартовый текст для второго сообщения в новый чат

После вставки первичного протокола можно отправить:

```md
Продолжай WMS-итерацию строго по handoff:
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/HANDOFF_TO_NEW_CHAT_STRICT_WMS_GATE_RU.md

Не продолжай старые ошибки: оркестратор не пишет код и UI сам. Каждая правка идёт через изолированных агентов. Product acceptance означает только живое браузерное прокликивание отдельным Product Browser Agent. Сейчас release заблокирован Final Integration Review; нужно доделать R01/R02/R03, потом повторить final integration review, потом общий browser regression, и только потом staging на Railway.
```
