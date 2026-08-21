# Наряд · 20260821-pdf-chestnogo-znaka-importirovat-tolko-p

**Полоса:** обычная
**Тип:** экран/существующий PDF-путь
**Заведён:** 21.08.2026 17:55

## Просили дословно

> PDF Честного знака: импортировать только полный КИЗ, декодированный из DataMatrix (GS + 91 + 92/93), проверять текстовый GTIN+serial и отклонять недекодированные/несовпадающие этикетки; восстановление только dry-run доступных кодов без привязанных/использованных

## Экраны

- экраны не назначены (новый экран или не UI-задача)

## Границы правки

Разрешено трогать только эти файлы:

- `backend/app/api/fbs_errors.py`
- `backend/app/cli/restore_truncated_marking_cis.py`
- `backend/app/services/fbs_kiz_service.py`
- `backend/app/services/fbs_marking_service.py`
- `backend/app/services/marking_code_service.py`
- `backend/app/services/marking_datamatrix_service.py`
- `backend/app/services/marking_import_storage_service.py`
- `backend/app/services/marking_label_artifact_service.py`
- `backend/pyproject.toml`
- `backend/tests/marking_datamatrix_test_helpers.py`
- `backend/tests/test_fbs_kiz.py`
- `backend/tests/test_marking_cis_pool_gs_separator.py`
- `backend/tests/test_marking_pdf_label_artifact.py`
- `backend/uv.lock`

## Статус

- [ ] арх-решение — не требуется: меняется существующий PDF-путь импорта КИЗ
- [x] контракт (обычная полоса): экран/API/данные/тесты описаны в просьбе владельца; текст PDF — только сверка GTIN+serial, запись — только декодированный DataMatrix с GS и AI(91), mismatch/undecodable — явный skip/reject
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260821-pdf-chestnogo-znaka-importirovat-tolko-p/`
- [ ] влито
