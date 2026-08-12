# B01 sanitized Browser state/network log

## Среда

- Surface: Codex in-app Browser only.
- Target: Railway staging web (`web-production-9e7c1.up.railway.app`).
- Viewports: 1280×720 and 1920×1080; DPR 1.
- Secrets, password values, tokens, cookies, localStorage and credential dashboards не читались и не записывались.
- Browser network interception не использовался. Сетевой результат фиксировался только через видимое состояние страницы, route, error/success UI и reload read-back; поэтому здесь нет выдуманных HTTP-кодов.

## Обезличенные состояния

| ID | Role/surface | Action | Visible/read-back outcome |
|---|---|---|---|
| S01 | FF auth | Existing synthetic session → root | Короткое «Загрузка профиля…», затем `/app/ff/dashboard` |
| S02 | FF admin | Dashboard 1280 | viewport 1280, document width 1280, height 1288 empty tenant / 1430 populated tenant |
| S03 | FF admin | Dashboard 1920 | DPR 1, document width 1920, height 1265; calendar visible |
| S04 | FF admin | Previous week | Week changed to 2026-08-03—2026-08-09; reload returned current week |
| S05 | FF admin | Main nav | Every advertised main item opened and `aria-current=page` was present |
| S06 | FF admin | Catalog at 1280 | viewport width 1280, document width 1727: right columns/actions clipped |
| S07 | FF admin | Notification popover/list | 2/9 visible notifications depending synthetic tenant; list route had no active sidebar item |
| S08 | FF admin | Back/forward/reload | settings ↔ notifications history restored; reload retained route and data |
| S09 | FF auth | Logout | Public login visible; URL remained previous protected route; browser fields could be prefilled, values not logged |
| S10 | FF auth | Invalid email syntax | Clear field-level/API validation error; no authenticated shell |
| S11 | FF auth | Valid-format wrong credentials | «Неверный email или пароль.»; correction led to dashboard |
| S12 | FF admin | Populated inbound row | Plain `<tr>`, pointer cursor, no role/tabindex/aria-label; click opened «Приёмка №000005» |
| S13 | FF admin | Dialog close | Dashboard restored without losing route |
| S14 | FF admin | Create synthetic seller | Success notice visible; reload found one matching synthetic row |
| S15 | Seller auth | First login | Password autofill remained non-empty after programmatic clear; keyboard select+delete made it empty and opened password setup |
| S16 | Seller auth | Cancel / mismatch | Cancel returned to login; mismatch showed «Пароли не совпадают.»; corrected values led to `/seller/documents` |
| S17 | Seller landing | 1280 | viewport/document width 1280; CTA visible; role label shown as `fulfillment_seller` |
| S18 | Seller landing | 1920 | DPR 1; no horizontal document overflow; role label still technical |
| S19 | Seller products | 1280 | viewport 1280, document width 1727; right columns clipped; empty data only |
| S20 | Seller nav | Four menu routes | Every main item opened with `aria-current=page` |
| S21 | Seller notifications | Popover/list/back/forward/reload | All routes recovered; notification list had no active sidebar item |
| S22 | Seller direct FF URL | `/app/ff/dashboard` | FF public login, not FF shell; no other tenant data visible |
| S23 | Seller unknown URL | `/seller/no-such-route-b01` | Replaced by `/seller/documents` with active Documents |
| S24 | Seller repeat login | Wrong password then correct | Clear error, correction returned to Documents |
| S25 | FF admin | Create synthetic staff + permissions | Staff row persisted after reload; reception and MP permissions checked |
| S26 | FF staff | First login | Password setup led to dashboard; topbar label «сотрудник»; menu contained only allowed blocks plus Dashboard/Sorting companion |
| S27 | FF staff | Direct sellers | Screen reachable, no tenant rows, explicit «Добавление селлеров доступно только администратору» |
| S28 | FF staff | Direct settings | Redirect/replaced to dashboard |
| S29 | FF staff | Reception | Populated row visible; status text was raw `receiving` |
| S30 | FF staff | MP shipments | Raw `forbidden` visible together with selector, create CTA and populated document rows |

## Screenshot inventory

`b01-001`…`b01-064` are present in this directory. Filenames contain role, action, viewport and sequence. Synthetic email addresses visible in screenshots are isolated test identifiers; no password value is visible.
