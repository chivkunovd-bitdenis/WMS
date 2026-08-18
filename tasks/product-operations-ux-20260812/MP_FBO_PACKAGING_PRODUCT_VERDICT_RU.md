# Product verdict: MP/FBO shipment and packaging

Статус: `product_approved`
Формат проверки: изолированный read-only продуктовый review по локальным документам, коду экранов и e2e-сценариям.

## Вердикт

ГИБРИД.

MP/FBO-отгрузку не нужно оставлять в прежнем перегруженном виде. Ее нужно привести к FBS-подобной операторской последовательности:

`план -> подбор -> упаковка/маркировка -> короба -> печать/финал`.

Но MP/FBO нельзя сливать с FBS как одну бизнес-сущность. Общим должен быть только понятный складской каркас, а доменная логика должна остаться отдельной.

## Почему

Для сотрудника fulfillment физическая работа похожа: увидеть план, подобрать товар, упаковать, разложить по коробам, напечатать нужное и завершить. Поэтому визуальная и процессная последовательность должна быть узнаваемой.

Но FBS в WMS связан с WB-заказами, FBS-поставкой, стикерами заказов, КИЗ/metadata, маршрутами ПВЗ или склад/СЦ и передачей заказов в доставку. MP/FBO-отгрузка работает по строкам товара и количествам. Если перенести FBS-сущности в MP/FBO, экран станет формально красивым, но складской процесс будет неверным.

## Что переносить из FBS

- спокойный MUI-экран с одним главным следующим шагом;
- шаги `план`, `подбор`, `упаковка/маркировка`, `короба`, `финал`;
- scanner-first поведение;
- общий контур упаковки через `PackagingTask`;
- общую печать ЧЗ/ШК через существующий диалог печати;
- понятный финальный gate: упаковка завершена, короба распределены, маркировка готова.

## Что не переносить из FBS

- QR каждого WB-заказа;
- WB order sticker на каждую единицу MP/FBO;
- создание FBS-поставки;
- FBS deadline как модель MP/FBO-срока;
- order-level metadata/КИЗ;
- WB cargo-place QR без явного требования маршрута;
- FBS-статусы и polling как модель MP/FBO.

## Как проверить будущую реализацию

1. Открыть MP/FBO-отгрузку от черновика до финала.
2. Убедиться, что оператор видит последовательность `план -> подбор -> упаковка/маркировка -> короба -> печать/финал`.
3. Проверить, что в MP/FBO нет FBS-заказов, QR каждого заказа и FBS-поставки.
4. Пройти FBS отдельно по маршрутам ПВЗ и склад/СЦ и убедиться, что утвержденный FBS baseline не сломан.

## Проверенные локальные источники

- `AGENTS.md`;
- `docs/MVP_DECISIONS_RU.md`;
- `docs/PACKAGING_RU.md`;
- `docs/UI_DESIGN_SYSTEM_RU.md`;
- `docs/reviews/product-operations-ux/MASTER_PRODUCT_UX_REVIEW_RU.md`;
- `tasks/fbs-operator-flow/FINAL_FBS_UI_HANDOFF_2026-08-06_RU.md`;
- `frontend/src/screens/ff/FfPackagingPage.tsx`;
- `frontend/src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx`;
- `frontend/src/components/SellerMarketplaceUnloadDialog.tsx`;
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`;
- `backend/app/models/marketplace_unload.py`;
- `backend/app/models/packaging_task.py`;
- `backend/app/services/fbs_packaging_integration_service.py`;
- `backend/app/services/fbs_packing_box_service.py`;
- `frontend/tests-e2e/ff-mp-packaging-gate.spec.ts`;
- `frontend/tests-e2e/ff-mp-packaging-print.spec.ts`;
- `frontend/tests-e2e/ff-packaging-page.spec.ts`;
- `frontend/tests-e2e/ff-fbs-full-flow.spec.ts`.
