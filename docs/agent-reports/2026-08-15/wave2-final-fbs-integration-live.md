# Wave 2 final FBS integration live

Экран / сценарий: FBS сквозной путь — новые заказы -> сборка поставки -> подбор -> упаковка и печать -> короба -> передача в WB.
Стадия: финальная интеграция после экранных приемок.
Статус: PRODUCT_BROWSER_APPROVED после исправления счетчика нанесенных стикеров.
Commit: 9d814943f7a48575250d8d6eefbd596c508ba341.
Раунд: 1.

## Browser

Открывал настоящий внешний Google Chrome `151.0.7922.138`, видимое окно ОС, CDP `127.0.0.1:9242`.
Управление: CDP mouse/key events в видимом окне Chrome. Playwright/headless не использовался как приемка.

Стенд:
- Backend: `http://127.0.0.1:18940`, SQLite `/private/tmp/wms_final_fbs_live_1786808276.sqlite`.
- Frontend: `http://127.0.0.1:18941`.
- WB-слой: локальный штатный e2e mock для Marketplace supplies/marking/warehouses; реальные секреты и живой кабинет WB не открывались.

## Proklikano

1. Вошел в FF-портал через форму логина.
2. Открыл `FBS`, вкладка `Новые`, увидел два заказа WB `998324` и `998325`.
3. Выбрал оба заказа, открыл `Сформировать поставку`, увидел совместимый preflight `Можно создать поставку`.
4. Создал поставку `FBS 15.08.2026`, открыл состав, нажал `Начать работу с поставкой`.
5. В подборе подтвердил ячейку `FBS-A-08324`, дважды просканировал товар `FBS-LIVE-BAR-1786808324`.
6. В упаковке открыл preview стикера WB для каждого заказа и подтвердил нанесение.
7. На живом UI нашел дефект: первый заказ имел `sticker.applied_at`, но счетчик оставался `Напечатано 1 из 2`, потому что frontend смотрел только на `sticker.status`. Исправлено: applied_at тоже считается фактом нанесения. После hot reload и повторного открытия той же поставки UI показал `Напечатано 2 из 2`.
8. Нажал `Все упаковано`, перешел на `Короба`, создал короб 1, добавил в него 2 товара.
9. Нажал `Передать в WB`, увидел блок `QR поставки WB`, открыл preview QR поставки и подтвердил нанесение.

## Final backend readback

`docs/agent-reports/2026-08-15/assets/wave2-final-fbs-live-evidence.json`:

- Supply `796204ed-2b5e-4d89-819b-03718a329c52`: `status=in_delivery`, `stage=tracking`.
- Progress: `picked=2`, `packed=2`, `metadata_ready=2`, `stickers_ready=2`, `total=2`.
- Orders `998324`, `998325`: `status=in_delivery`, `pick=picked`, `pack=packed`, `sticker_applied=true`.
- Box 1: assigned both order ids.
- Supply QR: `kind=supply_qr`, `status=ready`, `applied=true`, `preview_url=true`.

## Screenshots

- `assets/wave2-final-fbs-00-os-visible-chrome.png` — OS-visible Chrome window.
- `assets/wave2-final-fbs-02-new-orders.png` — FBS new orders.
- `assets/wave2-final-fbs-04-create-preflight.png` — compatible create supply preflight.
- `assets/wave2-final-fbs-07-location-confirmed.png` — location scan confirmed.
- `assets/wave2-final-fbs-09-order-998324-sticker-preview.png` and `assets/wave2-final-fbs-09b-order-998325-sticker-preview.png` — two WB sticker previews.
- `assets/wave2-final-fbs-10d-stickers-applied-after-fix.png` — live UI after fix: `Напечатано 2 из 2`.
- `assets/wave2-final-fbs-14-box-filled.png` — box filled `2 из 2`.
- `assets/wave2-final-fbs-15-delivered.png` — delivered state with supply QR block.
- `assets/wave2-final-fbs-16-supply-qr-preview.png` — supply QR preview.
- `assets/wave2-final-fbs-17-final-ui.png` — final UI after QR applied.

## Tests

- `npm run build` in `frontend/`: passed, Vite chunk-size warning only.
- MP/FBO regression targeted suite after `Rawls` merge: `19 passed in 31.21s`.
- Full backend suite: will be run after this report commit.

## Findings

Стоп: 0.
Тормоз: 0.
Хвост: 1 — final local run used the configured WB e2e mock, not a real WB cabinet smoke. This is intentional for this local integration gate; live external WB requires separate explicit credentials/action.

## 6a audit

Every visible control used in this scenario maps to existing FBS tasks: new orders selection and create supply (`FBS-02..05`), active supply/workspace (`FBS-18`, `FBS-20`), picking scan (`FBS-07/08`), print/QR preview and applied confirmation (`FBS-09..11`, `FBS-21`), boxes (`FBS-12`), delivery handoff and supply QR (`FBS-20/21`).
