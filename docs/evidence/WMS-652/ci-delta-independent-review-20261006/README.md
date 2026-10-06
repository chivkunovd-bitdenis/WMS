# WMS-652: независимое ограниченное ревью CI и геометрии

Вердикт **PASS для реализации в указанной области**. Новых технических дефектов
не найдено. Это не итоговая приёмка релиза, не активная защита GitHub и не
доказательство полного зелёного CI или достижения 10–15 минут.

Ревью выполняет отдельная сессия Sol 6.1. Прочитаны обновлённые origin/etalon
AGENTS.md, правила checkout, owner-cases и failure-cases целиком; применены
ограничения на область работы и различение исходников/локальных проверок/CI.
Рабочая ветка `codex/wms652-ci-delta-review`, исходный проверяемый SHA
`93b0757103fbd29fb00d4f198f6baab8def85172`. Реализация CI
`a642dc67ad24a5b56f0cad7645d1b8534a7fcc88` включена в `793c068e3`.
Контроль продукта `a5979fc311b88c07dace842a5786a7eefa48ea03`, контракт до кода
`9bb8b93254a7f79da7d8fd73eedfa75a1cf69b41`.

## Исполненные проверки CI

Из постоянной worktree независимо выполнены 20 новых CI контрактов и 51
product-scope контракт: **71 passed, 45 subtests passed**, 26.79s, сырой JUnit
`contracts.xml` и `contracts.log`. Отдельно **48 existing contracts PASS**,
`existing-contracts.log`. Настоящий CLI `product_scope.py --root . --trusted-ref
d61805978b3e7878d1056c99b4e6e0823edf49a5` дал exit 0 и пустую продуктовую дельту.
Ruff по runner/scope и mypy по runner PASS.

Свежий `pytest --collect-only -n 0` с теми же двумя прежними ignore собрал
**4625** уникальных случаев за 13.18s без исполнения тел тестов. Независимый
probe проверил разбиение **2313/2312**, точное объединение и ноль пересечений.
Все **600** protected full-backend names входят в свежий collection. Это
количество собранных тестов, а не 4625 выполненных PASS.

Прочитана реальная `.github/workflows/ci.yml`: matrix ровно два индекса,
fail-fast:false, `backend` сохраняет обязательное имя и requires success обоих
producer jobs. Отрицательные shell сценарии исполняют actual gate. Runner
собирает полный набор до фильтрации, сверяет digest каждого xdist worker,
добавляет исходный node ID в JUnit. Merger требует обе точные части и
SHA/run/attempt, отвергает пропуски/дубли/подмены и required skip, сохраняет
failure/error/skipped details; collection/setup error и nonzero exit не зелёные.
Настоящий synthetic xdist контракт запускает обе части и объединяет их.

Структурно сравнены прежний backend job (`d6d411438^`) и backend-checks:
PostgreSQL services и прежние steps совпадают после исключения перенесённого
full pytest/upload и единственного добавления PG517 JUnit. Изолированные PG662,
прочие PG сценарии, миграции, lint/native print остаются. Redis executable
проверяется/устанавливается до shard; обе ветви setup покрыты actual shell.
Frontend и print идут параллельно, process-proof требует оба результата.
Raw artifacts и guard reports передаются с именами конкретной попытки CI.

Diff CI диапазона `d6d411438^..793c068e3` по backend/app, backend/alembic,
backend/tests и frontend/src пуст. Frozen shard tests отличаются от precode
лишь explicit `check=False` в subprocess; failclosed — удалением unused json
import. Product-scope test diff `9bb8b9325..a5979fc31` пуст. Ожидания не ослаблены.

## Дополнительная ограниченная проверка geometry10

Прочитаны новые geometry.mjs, geometry-mutations.py, browser wiring, contract
и raw JSON. Точный исходник `1c045a4f2d6c1bb34eeed2f5e79f6e53be2a8a9d`,
доказательства `d6e39bb4fdf97a046f2c34a7b4d4e00345daa835`.
Новый набор измеряет реальный DOM/границы колонок и текста в Chrome1600×1000,
pointer reachability действий, точные print/preflight HTTP параметры и
переходы вкладок семи допустимых packing entries; два non-New order lists и
long-data selection дополняют их до10. Общий список43 сохраняет исходные33.
Chrome запускается с --mute-audio. Проверка не повторяла прежний browser run.

Независимый probe прочитал evidence из Git: final report имеет exact source SHA,
ровно43 упорядоченных уникальных ID и43 PASS. Каждый из трёх mutation reports
содержит полный тот же список43; адресные failure counts **7/2/1**, остальные
**36/41/42 PASS**. Причины — actual visibility/pointer или column overlap,
а не setup/пропуск. Source mutation helper восстанавливает product bytes в
finally. Geometry/assertions/cases неизменны между mutant source695 и final1c;
последняя дельта — только readonly Ozon documents GET fixture для вкладки Boxes.
Два сохранённых скриншота просмотрены визуально и приложены здесь: смешанная
упаковка и expired orders; длинные строки читаются, таблица штатно прокручивается.
Product не изменён. Это ограниченная проверка на одном viewport/synthetic HTTP;
live marketplace, app-shell/staging и физическая бумага не проверялись.

## Что обязательно завершить при интеграции

На reviewed SHA policy содержит прежние15 suites и ещё **не** регистрирует
backend_shards.py и четыре новых test files, ни exact suites reports
`ci-shards.xml`, `product-scope.xml`, `wms517-mac.tap`. Scope source/test files
уже находятся в files policy, но исполнение51 ещё не является обязательным
named report набором. Реальный новый CI YAML пока также отличается от прежнего
policy checksum. Это известная незавершённая интеграция, подтверждённая ведущим:
нужно закрепить окончательные files/commands/reports и acceptance до freeze/CI.
Для geometry нужна окончательная closure12/exact43 регистрация. Нового full
CI не было, скорость10–15 минут не измерена. Активация доверенного anchor/rules,
приёмка пакета и deploy находятся вне этого PASS. Main/GitHub/runtime не менялись.

Reviewer changes ограничены этим evidence каталогом. `probe.py` воспроизводит
независимую проверку сохранённых результатов и свежего collection; `probe.log`
и `workflow-review.json` сохраняют вывод. Merge в main не выполнялся.
