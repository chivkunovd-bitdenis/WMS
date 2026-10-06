# WMS-661 · Проверки механической интеграции

Проверенный продуктовый интеграционный SHA:
`4825b17df722f6b7200d6f4f57fe23b3e33493d9`.
Предшествующие коммиты: документы `52a9da6d334c31bf40214dde00b3f36eba7cbe4d`,
контракт `9121085109c8caa53f7d0d2ad7d9ebd93b1d7028`,
сохранение RED `7b0bb9bcc` (полный SHA доступен в истории).

## Локальные проверки

Из tools/support_agent, exit 0:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_agent_tools.py tests/test_readonly_mcp.py tests/test_agent_coordinator.py tests/test_agent_history.py tests/test_model_migration.py tests/test_wms661_precreation_search.py tests/test_wms661_minimal_support.py -q --tb=short -p no:cacheprovider
........................................................................ [ 50%]
......................................................................   [100%]
142 passed in 2.43s
```

142 PASS включают 62 неизменённые проверки окончательного контракта и 80
существующих смежных проверок. До продукта сохранены точные шесть исходных RED
и 56 GREEN в [полном логе](wms661-ordered-integration-red.md).
Ожидания, входы и фикстуры интегратор не менял.

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m ruff check --no-cache tools/support_agent/support_agent/agent_tools.py tools/support_agent/support_agent/readonly_mcp.py
All checks passed!

python3 scripts/ci/check_task_documents.py 8cd8db61598e6c80c91d7eff13301230a4ca6102
Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают.

python3 scripts/ci/check_task_documents.py origin/etalon
Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают.
```

Обе проверки документов завершились exit 0 на продуктовой интеграции;
origin/etalon = `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`.
Это проверка документов, не положительная приёмка: исходные вердикты постановки
и C8 не переписаны интегратором. Итоговый документальный SHA также подлежит
проверке обоими диапазонами перед push.

## Проверенное совпадение источника и результата

`git diff b5a79e3e8ca8c16039770471501a0d11a9a010f9 --` по трём продуктовым
файлам пуст. Их hash-object: `20f1f8cc2162ab17b907f3cf4f5642875631cdef`,
`b12c3645ec2447c6d0295914a4a9c6d7058de0a0`,
`86d1e1d1182d0320c334a31e0832de3575181fa4` соответственно.
Тесты совпадают с db5: `559159ea5f1c3187661277c79046f680918aaca2` и
`20ea64ba833c4a66cbb529378c860ba045a436e1`. Соответствие путей и immutable
ссылки перечислены в [передаче происхождения](HANDOFF-WMS-661-ORDERED-INTEGRATION-20261006.md).
Сохранённый Astra-отчёт также побайтово совпадает с исходником 0c19.

Относительно установленной базы нет изменений `scripts/ci`, `guards`, AGENTS.md,
CLAUDE.md или иного продуктового файла. Не перенесены mutable handoff в тестовый
контракт, quiet-изменения или продукт из etalon. Исходная ветка и все её коммиты
сохранены; чужие восемь untracked result-файлов остались на месте.

## Передача Root

Необходим следующий отдельный этап: приёмка Root/Sol-аналитиком на опубликованном
итоговом SHA. Интеграция не является новой авторской реализацией или новым
независимым ревью. Сохранённый Astra high PASS относится к точным исходным blobs;
его ограничение ENOSPC и собственные 10 PASS не скрыты локальным результатом
интегратора. PR и полный CI не инициированы интегратором.

Не проверены реальный смысловой выбор модели, рабочие чаты/Trello, установленная
служба и стенд. Браузер, управление секретами, печать, внешняя отгрузка, вывод
КИЗ и деплой не выполнялись. Новые зависимости, базы и worktree не создавались;
прогоны использовали только уже предусмотренные тестовые фикстуры.
