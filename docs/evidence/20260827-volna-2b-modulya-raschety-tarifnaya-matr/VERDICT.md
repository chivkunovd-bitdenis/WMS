# Вердикт живого экрана S-19 — волна 2Б

Дата проверки: 27.08.2026. Живой browser verdict: **ACCEPTED**.

На 1600px `documentWidth` равен viewport (`1600`). Подписи SelectInput и
MoscowDateTimeInput не пересекаются со значениями. В строке товарной цены
отображаются `17,50` и московское время `27.08.2026, 10:09`, без технической
UTC ISO-строки. Живой сценарий сохранил общую ставку 100 ₽, товарную 17,50 ₽ и
ставку сотрудника «Подбор» 33,50 ₽; оператор увидел «Матрица сохранена».

На 375px чип «Отдельно» помещается (`scrollWidth == clientWidth`). Ширина
документа 1356px и панели 1048px унаследована от старого S-19 shell/content;
волна 2Б её не вызвала и не меняет.

Машинные доказательства: tariff Playwright — 6/6; targeted backend — 20
passed, 4 skipped; PostgreSQL CHECK/race/composite-FK — 3 passed; изолированный
Alembic 0111→0112→0113 upgrade/downgrade/re-upgrade — 1 passed; ruff, mypy,
tsc, build, ui_guard, check_migrations, back_guard и `git diff --check` — exit
0. Единственное предупреждение build — существующий Vite notice о bundle >500kB.

Общий prerequisite ui-kit, который устранил перекрытие label для native
SelectInput и MoscowDateTimeInput: `ac9918449c160230ac091d8d42ded4accd14e04b`
(`fix(ui-kit): keep native field labels clear`).
