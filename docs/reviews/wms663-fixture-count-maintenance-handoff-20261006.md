# WMS-663 — maintenance ожидания количества fixture-пар

06.10.2026. Прямо разрешённая процессная правка после регистрации
`efe89d1d8fa704bd1e26f29b4351a3d3e4cb35bf`: единственная строка теста
`test_fifth_pair_and_sequential_file_baselines` меняет точное ожидание
`len(checker.FIXTURE_BLOB_PAIRS)` с 5 на 6. Все пять старых entries,
отрицательные проверки и алгоритм допуска сохранены; продукт, реестр и
требования не менялись.

До правки целевой тест: FAIL, `AssertionError: 6 != 5`, 1 test, 2.784 s.
После правки `PYTHONPATH=scripts/ci python3 -m unittest -v
test_wms663_positive_fixture_chain`: 4 tests PASS, 28.163 s. Это целевой тест
и существующие отрицательные случаи для assertion/name/skip/parameter/control
flow, extra paths/handoff/mode/review SHA и gap/order/review/source.
Полный 79-тестовый набор не перезапускался.

Собственные изменения: только строка счётчика в существующем тесте и этот
handoff. Ведущий передаёт регистрацию и правку счётчика вместе на Astra review;
эта сессия ревью не запускает. Browser, secrets, PostgreSQL, live, CI и deploy
не выполнялись.
