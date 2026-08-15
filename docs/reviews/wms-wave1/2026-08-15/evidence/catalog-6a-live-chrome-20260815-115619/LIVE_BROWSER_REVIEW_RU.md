# Live Chrome acceptance: Каталог товаров

Статус: SCREEN_APPROVED
Commit: 51e946f
Браузер: Chrome/151.0.7922.138, внешнее видимое окно Google Chrome, управление через CDP/DevTools, не headless.
URL: http://127.0.0.1:52962/app/ff/products

## Проверки

- PASS empty_state_visible
- PASS inventory_nav_hidden
- PASS seller_create_absent
- PASS search_filter_sort_absent
- PASS inventory_route_redirects_to_catalog
- PASS manual_product_visible
- PASS clean_name_no_duplicate_sku_vendor_size_barcode
- PASS name_single_line_long_data
- PASS manual_chip_absent
- PASS manual_product_api_readback
- PASS chz_icon_gray_zero_without_text_chip
- PASS chz_icon_yellow_count_two
- PASS chz_text_chip_still_absent
- PASS chz_icon_opens_product_codes_page
- PASS excel_template_downloaded_without_quantity
- PASS excel_preview_good_no_quantity_column
- PASS excel_products_persist_after_reload
- PASS excel_error_duplicate_visible_apply_disabled

## Ведра

- Стоп: 0
- Тормоз: 0 открытых; 8 закрыто rework/6а
- Хвост: 1, не-каталожный DOM warning на странице карточки Честного знака из предыдущего наблюдения, в catalog scope не исправлялся.

## Скриншоты

- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/01-empty-catalog.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/02-manual-create-filled.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/03-manual-product-row.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/04-chz-yellow-count-two.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/05-chz-product-page-opened-tail.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/06-excel-preview-good.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/07-excel-apply-success.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/08-excel-products-after-reload.png
- /Users/deniscivkunov/Projects/WMS/.worktrees/wave1-catalog-20260814/docs/reviews/wms-wave1/2026-08-15/evidence/catalog-6a-live-chrome-20260815-115619/09-excel-preview-duplicate-error.png
