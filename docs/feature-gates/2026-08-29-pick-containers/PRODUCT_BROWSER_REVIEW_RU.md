# Product Browser Review After Dev: физическое место товара в подборе

Карточка `PICK-CONTAINERS-01` не может получить положительную продуктовую
приёмку в браузере на этом проходе. Реализация расширяет только backend-ответы
двух `pick-options`, а пользователь прямо запретил менять frontend и запускать
его проверки: новые поля будет подключать к экрану другой человек.

В текущем frontend нет потребления `sources`, `container_path`, `source_label`
или `is_loose`. Экран подбора отгрузки продолжает строить место по прежним
`storage_location_id` и `location_code`. Следовательно, видимая вкладка сейчас
не способна показать оператору палету, короб, грузоместо, вложенный путь или
признак «Россыпью», даже если backend уже возвращает эти данные.

API-запрос, чтение кода, pytest или эмуляция ответа не заменяют обязательный
живой проход по интерфейсу. Я не открывал и не запускал frontend, не выполнял
npm/Playwright и не пытался обойти blocker через API/curl — это соответствовало
явным границам исходной задачи.

## Обязательный verdict

```yaml
feature_id: PICK-CONTAINERS-01
agent_name: /root/product_browser_pick_containers
isolated_agent: yes
review_stage: after_dev
professional_context:
  wms: yes
  logistics: yes
  fulfillment: yes
  marketplaces_wb: yes
real_browser_used: no
browser_type: null
environment_url: null
role: "Product Agent after development; складская роль в UI не использовалась"
tenant: "не выбран: живой UI не запускался"
seller: "не выбран: живой UI не запускался"
warehouse: "не выбран: живой UI не запускался"
screen_urls: []
actions_clicked: []
inputs_or_scans: []
success_seen: >-
  Не проверен в UI: новые сведения о физическом источнике не подключены к
  frontend и поэтому не могут быть видимы оператору.
error_seen: >-
  Не проверен в UI: живой экран не запускался, а backend-ошибка
  invalid_container_reference не является браузерным доказательством сама по
  себе.
empty_state_seen: >-
  Не проверено в UI: живой экран не запускался.
reload_readback_seen: >-
  Не проверено в UI: не было видимого действия и результата, который можно
  перечитать после перезагрузки.
element_verdicts:
  rows: "BLOCKED: строки с физическими источниками отсутствуют в текущем UI."
  columns: "BLOCKED: frontend не менялся; отдельное отображение пути тары не подключено."
  buttons: "NOT_REVIEWED: реальная вкладка не открывалась."
  labels: >-
    BLOCKED: подписи Палета, Короб, Грузоместо и Россыпью из нового backend-
    контракта текущим UI не читаются; видимое Без ячеек по новой выдаче не
    проверялось.
  fields: >-
    BLOCKED: sources[].quantity, sources[].is_loose,
    sources[].source_label и sources[].container_path[] не подключены к типам и
    отрисовке frontend.
  filters: "NOT_REVIEWED: реальная вкладка не открывалась."
  chips: "NOT_REVIEWED: реальная вкладка не открывалась."
  statuses: "NOT_REVIEWED: реальная вкладка не открывалась."
  dialogs: "NOT_REVIEWED: реальная вкладка не открывалась."
  text_fit: >-
    BLOCKED: невозможно проверить длину и вложенность Палета -> Короб или
    Палета -> Грузоместо, пока эти значения не отрисовываются на экране.
warehouse_usability_verdict: >-
  Браузерная пригодность не доказана. В текущем интерфейсе оператор не получает
  от этой backend-карточки видимого указания, из какой именно тары снимать товар;
  оценить понятность, порядок вложенности и риск ошибочного съёма можно только
  после отдельного подключения полей к обоим экранам подбора.
demo_risk: >-
  Если показать текущий экран клиенту как результат этой карточки, обещанное
  различение палеты, короба, грузоместа и россыпи останется невидимым. Кроме
  того, без реального прохода нельзя подтвердить, что длинный путь тары не
  перегружает строку и не прячет основное действие подбора.
verdict: PRODUCT_BROWSER_BLOCKED
evidence_paths:
  - docs/feature-gates/2026-08-29-pick-containers/FEATURE_CARDS_RU.md
  - docs/feature-gates/2026-08-29-pick-containers/PRODUCT_BEFORE_DEV_RU.md
  - docs/feature-gates/2026-08-29-pick-containers/CODE_REVIEW_RU.md
  - backend/app/services/pick_option_location_service.py
  - backend/app/api/marketplace_unload_requests.py
  - backend/app/api/fbs_supplies.py
  - frontend/src/screens/ff/unload-pick/FfUnloadPickPage.tsx
  - frontend/src/screens/ff/FfMpUnloadPickPanel.tsx
blocking_issues:
  - >-
    BLOCKER-PICK-CONTAINERS-UI-01: новый backend-контракт sources[] с
    container_path[] не подключён к frontend, поэтому ни один живой экран не
    может показать оператору вид и номер тары, полный путь вложенности или
    признак Россыпью.
  - >-
    BLOCKER-PICK-CONTAINERS-BROWSER-02: исходная задача явно ограничена backend,
    запрещает менять frontend и запускать npm/Playwright; безопасного видимого
    сценария для browser review в границах этой карточки нет.
```

**Product verdict: `PRODUCT_BROWSER_BLOCKED`.** Для повторного review нужна
отдельная frontend-карточка, которая подключит добавочные поля к обоим подборам,
а затем живой стенд с подходящими остатками: россыпь, прямая палета, короб,
грузоместо, вложенная тара и место «Без ячеек». Только после этого отдельный
Product Agent сможет открыть видимую вкладку, пройти сценарии руками и выдать
один из итоговых browser-verdict.
