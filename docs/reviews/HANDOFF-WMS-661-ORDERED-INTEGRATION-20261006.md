# WMS-661 · Механическая упорядоченная интеграция · 06.10.2026

Роль: mechanical INTEGRATOR661, не автор постановки, новых тестов или продукта.
Прямое поручение Root разрешает продолжить установленную базу
`8cd8db61598e6c80c91d7eff13301230a4ca6102` вместо смешивания с кодом etalon,
чтобы сохранить совместимость runtime бота. Установка службы этим не проверяется.
Свежие правила прочитаны из `origin/etalon` =
`4b298efc95be7b4b6b7fe5665be9f3671f1fe747` (fetch ранее выполнен Root).
Навыки, новые агенты, браузер, секреты, внешние операции и деплой запрещены.

В том же worktree после чистой проверки отслеживаемых файлов создана ветка
`codex/wms661-reviewed-ordered-integration` от указанной базы. Все untracked
`urgent661_*` сохранены. Исходная ветка `codex/wms661-installed-baseline-tests`
и её remote подтверждены на `0c19ed425106f1ddf40e83de855a69b2c4fa3b54`;
их история не переписывается. Автор новых коммитов — интегратор; оригинальные
Git author, SHA и содержимое доступны по следующим неизменяемым ссылкам.

## Исходники и авторство

Во всех перечисленных исходных коммитах Git author —
Denis Civkunov <denischivkunov@icloud.com>. Исполнявшиеся роли различаются
в передачах; поле Git author не следует считать названием модели.

- Постановка Sol: [07efbe5832840d8e5b6917dfc7c5433102a3c5c1](https://github.com/chivkunovd-bitdenis/WMS/commit/07efbe5832840d8e5b6917dfc7c5433102a3c5c1), 2026-10-06T12:23:04+04:00.
  [Оригинальные требования](https://github.com/chivkunovd-bitdenis/WMS/blob/07efbe5832840d8e5b6917dfc7c5433102a3c5c1/docs/requirements/WMS-661.md)
  перенесены без изменения, blob `1104c649c652519a07925b16875aa765b4ebf2b8`.
- Перенос постановки на установленную базу: `97e5cfc08ef6d01613a04fd4dd4b7bad114fac37`, 2026-10-06T12:51:18+04:00.
- Исходный контракт отдельного тестировщика: `7d168b81393d0eefdaeebee010484c41cbe74443`, 2026-10-06T13:00:32+04:00.
  Усиление после ревью: `cc6b1b274bbfb7c31def404912f7f1533f70e81f`, 2026-10-06T13:08:03+04:00.
  PASS контракта сохранён в `ca2a51018f5c2cdc319350ea9932dad557cd6e24`.
- Окончательный контракт с непустым отрицательным входом:
  [db5e5425218201acc776588aa5a1c709e06840fc](https://github.com/chivkunovd-bitdenis/WMS/commit/db5e5425218201acc776588aa5a1c709e06840fc), 2026-10-06T13:22:49+04:00.
  [precreation_search](https://github.com/chivkunovd-bitdenis/WMS/blob/db5e5425218201acc776588aa5a1c709e06840fc/tools/support_agent/tests/test_wms661_precreation_search.py)
  blob `559159ea5f1c3187661277c79046f680918aaca2`;
  [minimal_support](https://github.com/chivkunovd-bitdenis/WMS/blob/db5e5425218201acc776588aa5a1c709e06840fc/tools/support_agent/tests/test_wms661_minimal_support.py)
  blob `20ea64ba833c4a66cbb529378c860ba045a436e1`.
- Продукт отдельного Sol-разработчика:
  [b5a79e3e8ca8c16039770471501a0d11a9a010f9](https://github.com/chivkunovd-bitdenis/WMS/commit/b5a79e3e8ca8c16039770471501a0d11a9a010f9), 2026-10-06T13:16:08+04:00.
  [agent_instructions.md](https://github.com/chivkunovd-bitdenis/WMS/blob/b5a79e3e8ca8c16039770471501a0d11a9a010f9/tools/support_agent/support_agent/agent_instructions.md)
  blob `20f1f8cc2162ab17b907f3cf4f5642875631cdef`;
  [agent_tools.py](https://github.com/chivkunovd-bitdenis/WMS/blob/b5a79e3e8ca8c16039770471501a0d11a9a010f9/tools/support_agent/support_agent/agent_tools.py)
  blob `b12c3645ec2447c6d0295914a4a9c6d7058de0a0`;
  [readonly_mcp.py](https://github.com/chivkunovd-bitdenis/WMS/blob/b5a79e3e8ca8c16039770471501a0d11a9a010f9/tools/support_agent/support_agent/readonly_mcp.py)
  blob `86d1e1d1182d0320c334a31e0832de3575181fa4`.
- Независимый Astra high PASS продукта и окончательного входа сохранён Root в
  [0c19ed425106f1ddf40e83de855a69b2c4fa3b54](https://github.com/chivkunovd-bitdenis/WMS/commit/0c19ed425106f1ddf40e83de855a69b2c4fa3b54).
  [Отчёт](wms661-astra-b5a79-db5e54.md) перенесён без изменения,
  blob `d221260b021a516364a11b3d73b99340e97d8953`.
  Ревьюер выполнил 10 PASS; полный 62 был заблокирован ENOSPC.
  Тестировщик ранее выполнил 62 PASS. Это не приёмка интеграционной ветки.

## Последовательность и границы доказательства

Сначала отдельный docs-only коммит с оригинальными требованиями и доказательствами.
Затем точные два окончательных теста из db5 и только ссылки «Тест» в требованиях
фиксируются коммитом `WMS-661: контракт тестов`; handoff в контракт не входит.
До переноса продукта ожидаются исходные шесть содержательных RED и 56 GREEN.
Если имена или причины отличаются, интеграция останавливается без изменения входов.
Далее переносятся ровно три продуктовых файла b5 с проверкой byte/blob identity.
Проверки повторяются с существующими небольшими смежными тестами.
Проверка документов запускается относительно 8cd8 и фактического origin/etalon,
без изменений checker, guards или протокола и без подбора удобной базы.

Приёмку проводит Root/Sol-аналитик отдельным этапом. До неё нет PR или полного CI.
Автоматические проверки используют подмену решения модели: способность реальной
модели распознавать смысловые дубли, рабочие Telegram/Trello и runtime не доказаны.
