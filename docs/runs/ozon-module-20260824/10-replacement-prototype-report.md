# S0R FBS local-fixture browser path

This is the exact browser script for the one existing FBS queue and one
existing FBS workspace. It is an implementation trace, not a product-browser
verdict. `ozonPrototype=1` is local fixture mode: none of the listed fixture
actions calls WMS stock, backend, provider, or credentials APIs.

## Entry and shared queue

1. Open `/app/ff/fbs?ozonPrototype=1`.
2. In the existing marketplace selector (`data-testid="ozon-fbs-marketplace-filter"`), choose visible value **Ozon**.
3. In the existing row `data-testid="fbs-order-ozon-fixture-4829"`, verify the real product cell says **Платье Margo × 2 · Блуза Luna × 1** and **Блуза Luna не сопоставлена**. The order cell says **Ozon posting 4829-0001-1** and **2 товара, 3 шт.** No table column is added.
4. Select that same real row through its existing checkbox. The ordinary `data-testid="fbs-selection-bar"` appears.
5. Click its `data-testid="ozon-fbs-selection-open"` button, **Открыть workspace**. This uses the existing selection-bar-to-workspace path; it only seeds local state.

## Existing workspace: exact transition path

1. In existing **Состав**, verify `data-testid="ozon-fbs-composition-blocker"`: **Блуза Luna не сопоставлена с WMS-товаром**. The composition table has three unit projections under one posting: Margo, Margo, Luna.
2. Click `data-testid="ozon-fbs-confirm-mapped-fixture"`, **Подтвердить mapped fixture**. Verify the success message that Luna is mapped locally.
3. Click `data-testid="fbs-start-work"`, **Начать работу с поставкой**. The existing workspace moves to **Подбор**.
4. In visible input **Штрихкод ячейки**, enter `B-00-00` and click **Подтвердить ячейку**. Verify local error: expected `A-01-02`.
5. Enter `A-01-02` and click **Подтвердить ячейку**. Verify the existing stage shows **Ячейка A-01-02 подтверждена**.
6. In visible input **Штрихкод товара**, enter `NOT-POSTING` and click **Подобрать товар**. Verify local wrong-product error.
7. Enter `MARGO-42` and click **Подобрать товар** twice. Verify two local Margo unit projections are picked.
8. Enter `MARGO-42` a third time and click **Подобрать товар**. Verify local duplicate/excess error.
9. Enter `LUNA-38` and click **Подобрать товар**. Verify the notice that the third unit moved the same workspace directly to **Упаковка и маркировка**.
10. In `data-testid="ozon-fbs-packing"`, verify `data-testid="ozon-fbs-exemplar-state"` begins rejected. Click `data-testid="ozon-fbs-exemplar-correct"`, **Исправить exemplar**; verify it becomes accepted locally.
11. Click `data-testid="ozon-fbs-create-partial-package"`, **Создать частичную упаковку 2 из 3**. Verify **Posting ещё не завершён** and that Luna remains to pack.
12. Click `data-testid="ozon-fbs-complete-third-unit"`, **Упаковать третью единицу и перейти к коробам**. The same workspace moves to **Короба**.
13. In `data-testid="ozon-fbs-boxes"`, verify **WMS короб №1 (WMS-BOX-4829-01) → Ozon package №1 → posting 4829-0001-1 (3 из 3 единиц)**.
14. Verify `data-testid="ozon-fbs-label-state"` starts **pending**. Click `data-testid="ozon-fbs-label-ready"`, **Подготовить label**, and verify **ready**.
15. Click `data-testid="ozon-fbs-label-applied"`, **Нанести label на package**, and verify **applied**.
16. Verify the current bottom handover area states discovered capability **сдача по одному** and that carriage is only an alternative. Click `data-testid="ozon-fbs-handover-one-by-one"`, **Передать posting по одному**.
17. Verify final visible `data-testid="ozon-fbs-handover-pending"` text exactly: **Передано WMS, Ozon ещё не подтвердил**. It is deliberately not an Ozon acceptance or delivery claim.

## Reuse and local-only checks

1. Remove `?ozonPrototype=1`, return to `/app/ff/fbs`, and verify the ordinary WB queue/workspace controls are present with no Ozon fixture row.
2. Run `python3 scripts/ci/check_ozon_reuse_scope.py --self-test`.
3. Run `python3 scripts/ci/check_ozon_reuse_scope.py --base HEAD --head WORKTREE` for this worktree diff.
4. Run `git diff --check` and `cd frontend && npm run build`.

The browser path intentionally does not use an API client, a provider request,
stock mutation, or credential surface.
