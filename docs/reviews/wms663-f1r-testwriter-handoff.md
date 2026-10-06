# WMS-663: независимый контракт тестов F1-R до исправления

06.10.2026. Замечание: `docs/reviews/wms663-astra-6ce78bc.md`, F1-R.
Тестируемый checkout: `f6d516b4b3a42ac66668ea83f3191e6c1310e294`.
Продуктовый сервис не отличается от проверенного
`6ce78bcc0a479951f60710138973e9563e6c1350`: проверено через git diff.

Добавлен только новый файл
`backend/tests/test_wms663_accepted_read_regressions.py` и эта передача.
Существующие тесты, требования и продуктовый код не изменены.
Использованы существующие `_accept_a`, `_scan`, `_seed_order`, `_transport`
и снимок `_remote_snapshot`. Сервисы настоящие, транспорт Ozon фиктивный.
База — отдельная SQLite conftest; внешние запросы не выполняются.

## Контракт и доказательство RED

Принять ГТД `001/ABC-09`, затем изменить кабинетный снимок экземпляра 81
на `NEW-GTD`/`NEW-RNPT`, оба признака отсутствия false, статус ship_available.
Обязательный промежуточный GET должен читать STATUS без SET/create-or-get,
показывать свежие значения и разрешать продолжение.

Три целевые проверки падают на неизменённом продукте:

- `test_f1r_accepted_get_shows_fresh_cabinet_and_remains_editable`:
  получено `001/ABC-09` вместо `NEW-GTD`.
- `test_f1r_accepted_get_allows_next_write_without_old_a[documents_b]`:
  настоящий save документа B выдаёт `ozon_exemplar_documents_conflict`.
- `test_f1r_accepted_get_allows_next_write_without_old_a[marking]`:
  настоящий submit_marking выдаёт тот же конфликт.

Обе проверки продолжения после исправления требуют ровно второй SET,
сохранения свежих документов, признаков отсутствия, массы и маркировок A,
а также присутствия нового документа B либо новой маркировки экземпляра 82.

Пять контрольных случаев проходят: GET и новый claim сохраняют блокировку
для unknown и активного writer; устаревшая версия отвергается для documents
и marking без изменения сохранённых данных; запоздавший GET версии 1
не перезаписывает document claim версии 2 с `NEW-INPUT`. Последний случай
использует две настоящие SQLite-сессии и перехват только вызова fake-provider.

Команда из backend:

```sh
env -u WMS_TEST_DATABASE_URL -u WMS_TEST_DATA_DIR \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  tests/test_wms663_accepted_read_regressions.py -n 1 -q --tb=short
```

Результат окончательной версии: **3 failed, 5 passed, 12 warnings in 5.68s**.
Ruff для нового файла: **All checks passed**.

## Передача разработчику

Исправить только продуктовый путь accepted → свежий GET → следующий документ/КИЗ,
сохранив контрольные защиты. Ожидания этого файла и ранее замороженных тестов
не менять. После исправления повторить новый файл и оба существующих набора
`test_wms663_astra_regressions.py`, `test_wms663_customs_documents_contract.py`.
Ожидается восемь зелёных новых случаев; RED является доказательством дефекта,
а не приёмкой продукта. Нужны последующие независимое ревью и приёмка.

Навыки и дочерние агенты не запускались. Кабинеты авторизации, секреты,
production и Telegram не использовались; merge/deploy не выполнялись.
Чужие незакоммиченные файлы оставлены без изменений.
