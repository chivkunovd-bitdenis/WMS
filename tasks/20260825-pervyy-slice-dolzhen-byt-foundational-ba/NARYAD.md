# Наряд · 20260825-pervyy-slice-dolzhen-byt-foundational-ba

**Полоса:** обычная
**Тип:** экран
**Заведён:** 25.08.2026 09:09

## Просили дословно

> Первый slice должен быть foundational backend/account/data model + existing seller settings connection surface

## Экраны

- `S-32` /settings — SellerSettingsScreen

## Границы правки

Разрешено трогать только эти файлы:

- `backend/alembic/versions/20260825_0101_marketplace_accounts.py`
- `backend/app/api/ozon_integration.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/marketplace_account.py`
- `backend/app/models/seller.py`
- `backend/app/services/marketplace_account_service.py`
- `backend/app/services/ozon_client.py`
- `backend/tests/test_marketplace_account_service.py`
- `backend/tests/test_marketplace_accounts_migration.py`
- `backend/tests/test_ozon_integration_api.py`
- `frontend/src/api.ts`
- `frontend/src/screens/v2/SellerSettingsScreen.tsx`
- `frontend/tests-e2e/seller-settings.spec.ts`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260825-pervyy-slice-dolzhen-byt-foundational-ba/`
- [ ] влито
