# WMS-652 C59: whole-candidate contract before implementation

Основание: analyst brief f3cc69509654702ae2b1e23c92be21a116529e78, существующий R48.
Для текущего процесса root независимо выбирает product anchor
`d61805978b3e7878d1056c99b4e6e0823edf49a5`: новые product changes652 не поручены.
Этот SHA не вшит как вечная product база внутрь callable: caller передаёт
конкретный independently trusted_ref; accepted upgrade fixture показывает
возможность следующего точного reviewed reference и сохранение запрета соседней
дельты. Автоматического получения owner consent из кандидата нет.

`verify_product_scope(root: Path, trusted_ref: str) -> list[str]` возвращает sorted
unique forbidden product paths. [] означает неизменённый product tree/index/
worktree, а не разрешение любой задачи по subject. Invalid/noncommit/missing
trusted reference/history, unborn HEAD, nonrepository и unmerged index должны
дать ValueError. Callable находится в будущем scripts/ci/product_scope.py;
тестировщик модуль не создаёт, реализацию ведёт root отдельным коммитом.

51 collected cases: current unchanged product + process additions; four subjects;
26 backend/frontend/shared-style/static-assets/runtime-config paths; четыре
local phases включая index delta, отменённую только в worktree; ignored new
source; deletion/rename/rename-to-test; imported foreign merge; own merge
resolution; candidate self-approval; explicit reviewed upgrade и neighboring
rejection; invalid/missing/ref-as-blob; nonrepository/unborn/unmerged; unique
sorted paths и read-only verification.

Включены backend/app/backend/alembic; frontend/src с явным существующим test
suffix pattern *.test.[cm]?[jt]sx?; frontend/public, root HTML/seller entry,
vite/tsconfig/package manifests/screens registry, Dockerfile/railway/frontend
webserver configs и actual build-invoked verify-cryptopro-vendor.mjs. Other
CI/deploy/scripts/guards — отдельный процесс/freeze контур и исключены из этой
product policy; test/docs additions также исключены. Не разрешён широкий
screens/v2 либо исключение по словам test в filename. .gitignore не может
маскировать новый исполняемый source. Никакие реальные WMS files/HEAD/index
в Git-fixture не меняются: каждый case создаёт только synthetic mini-repository.

До реализации сохранён before-implementation-red.log: ожидаемый ERROR отсутствия
нового callable, **это не meaningful product/scope RED** и не закрытие C59.
После реализации root обязан реально исполнить случаи и purposeful scope
mutations, сохранить GREEN/RED exact SHA; browser geometry идёт отдельным шагом.
Collection51/Ruff PASS, прежние wms666ChangeScope frozen expectations не менялись.

Команда из root:

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest scripts/ci/tests/test_product_scope.py -q
```

Dependency closure: scripts/ci/tests/test_product_scope.py (включая Repo fixture),
future scripts/ci/product_scope.py, Git + pytest runtime. Trusted selection and
required CI/protection remain root-owned; no registry/workflow changes here.
