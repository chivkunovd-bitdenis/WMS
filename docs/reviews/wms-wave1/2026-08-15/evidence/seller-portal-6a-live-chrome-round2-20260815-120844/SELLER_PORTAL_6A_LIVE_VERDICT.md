# Seller portal 6a live Chrome verdict Round 2

Commit: `f92f9d4cbeb72348aa374b8ce2e213cfdfc49c04`
Status: `SCREEN_APPROVED`
Browser: External visible Google Chrome via CDP (Chrome/151.0.7922.138)
URL: http://127.0.0.1:5183
Return request: `b3b833f8-9090-416c-adbb-d4889c64c344`

## 6a map

| Element | Task ID | Action |
|---|---|---|
| Блок Документы + подпись | REC-02/CAL-04/GLOBAL-02 | оставить |
| Кнопка Создать заявку на поставку | SEL-01..05/REC-08 | оставить |
| Кнопка Создать заявку на возврат | REC-02 | оставить |
| Блок Сегодня / Завтра | CAL-04 | оставить |
| Фильтр Тип документа | REC-02/GLOBAL-02 | оставить |
| Фильтр Сортировка | GLOBAL-02 | оставить |
| Колонки списка Тип/Дата/Накладная/Статус/Строк/Действия | REC-02/SEL-02/GLOBAL-01/02 | оставить |
| Форма возврата: дата/грузоместа/накладная/status chip/тип | CAL-04/REC-08/SEL-02/SEL-03/REC-02 | оставить |
| Кнопки Добавить товары/Сохранить/Закрыть/Передать на склад | SEL-01/SEL-04/REC-08/GLOBAL-02 | оставить |
| Picker: поиск/категории/Выбрать все/Проставить всем/таблица/qty | SEL-01/SEL-04 | оставить |
| Кнопка печати ШК в строке + ProductBarcodePrintDialog | SEL-05 | оставить |
| Синяя readonly-плашка Приёмку взял в работу склад | SEL-03 | оставить |
| Fact-card meta операция/status/склад | REC-02/SEL-03/GLOBAL-01 | оставить |
| Fact-card колонки Товар/Заявлено/Принято/Итог/Детали | REC-13/REC-14 | оставить |
| Красные строки расхождений и Итог Недостача/Излишек | REC-13/REC-14 | оставить |
| Зелёная подсветка совпавших строк | REC-13 | оставить |
| Блоки Итог приемки / Что не так | GLOBAL-02/REC-13 | удалены, оставить отсутствующими |

## Findings

- No findings.

## Screenshots

- `screenshots/01-seller-documents-actions-calendar-empty.png`
- `screenshots/02-return-draft-form-operation-readonly.png`
- `screenshots/03-picker-scan-select-all-bulk.png`
- `screenshots/04-rec08-empty-boxes-submit-guard.png`
- `screenshots/05-standard-product-barcode-print-dialog.png`
- `screenshots/06-submitted-return-calendar-waybill.png`
- `screenshots/07-ff-return-receiving-card.png`
- `screenshots/08-ff-red-green-and-added-line-before-complete.png`
- `screenshots/09-ff-discrepancy-dialog-return.png`
- `screenshots/10-seller-return-fact-card-readonly-no-summary-blocks.png`
