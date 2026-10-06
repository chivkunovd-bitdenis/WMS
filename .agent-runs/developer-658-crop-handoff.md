# WMS-658: исправление source-page/crop

База: frozen contract `16a58ac82df16fada0571d249b0827e8900527ad`, review
`24fcbdabc`. Правила AGENTS/developer skill прочитаны, дерево перед работой
чистое. Менять тесты и требования запрещено.

## Фактический результат до правки

Новый frozen test `test_c22_audit_accepts_unchanged_label_cropped_from_supplier_page`
на неизменённом продукте: **1 PASS**, 2.57 s, SQLite в памяти, pytest -n 0.
Декодер не завис. Helper `_framed_label_page` не рисует рамку: source 600x800,
0 drawings; настоящий parse_import_file сохраняет артефакт **600x800**.
Этот тест не воспроизводит вырезание 220x220 из review. Ожидания не изменены.

Дополнительный диагностический запуск в памяти обернул только helper страницы:
после исходного размещения вызвал `page.draw_rect(Rect(30,30,250,250))`.
Сами frozen assertions, auto-import, PDF print и audit не подменялись.
Результат до продукта: **1 FAIL**, 1.09 s, assertion
`report['first_divergence'] is None` (строка 1094). Это фактический RED
рамочного пути reviewer, а не RED исходного frozen файла.
Первый диагностический wrapper импортировал app до pytest fixture и получил
setup ERROR из-за локальной default PostgreSQL. Исправленный wrapper явно
задал DATABASE_URL и WMS_TEST_DATABASE_URL `sqlite+aiosqlite:///:memory:`;
его результат FAIL приведён выше. Production не использовалась.

## Продукт и проверки после исправления

Продуктовый commit: `6e9575ecfd83d1c933d8cf017c1aa071fb49ebeb`.
Изменён только `backend/app/services/marking_import_audit_service.py`.
Аудит выделяет source-этикетки существующим штатным экстрактором и выбирает
правильную область по полному payload. Сравнивается макет этой области с
сохранённой этикеткой, а не макет всего листа. Неоднозначные/недоступные
области оставляют `source_to_artifact_layout`. Сигнатуры текста, изображений
с hash содержимого и графики сохранены, как и final_print_layout detection.
WB nmID guard не изменялся.

Адресные frozen tests на итоговом audit-коде: **5 PASS, 0 skip**, 4.97 s:

```sh
PYTHONDONTWRITEBYTECODE=1 WMS_TEST_DATABASE_URL=sqlite+aiosqlite:///:memory: \
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  -n 0 -p no:cacheprovider -q --tb=short -o faulthandler_timeout=60 \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_accepts_unchanged_label_cropped_from_supplier_page \
  tests/test_wms658_marking_import_contract.py::test_c22_incident_audit_is_read_only_and_reports_first_divergence \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_reports_source_to_saved_label_substitution \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_reports_raster_final_label_substitution \
  tests/test_wms658_wb_honest_sign_contract.py::test_c19_c20_backfill_rejects_raw_nmid_that_does_not_belong_to_product
```

Дополнительный рамочный путь: **1 PASS**, 3.92 s. Настоящий парсер явно
показал `ACTUAL_CROP_SIZE (0,0,220,220)`, затем прошёл тот же frozen сценарий
auto-import → result PDF → audit с `first_divergence=None`, `evidence_gaps=[]`.
Воспроизводимый диагностический wrapper (выполнять из backend):

```sh
PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite+aiosqlite:///:memory: \
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:///:memory: \
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, 'tests')
import fitz
import pytest
import test_wms658_marking_import_contract as contract
from app.services import marking_code_service as marking
original = contract._framed_label_page
def with_frame(label_pdf):
    with fitz.open(stream=original(label_pdf), filetype='pdf') as doc:
        doc[0].draw_rect(fitz.Rect(30, 30, 250, 250))
        source = bytes(doc.tobytes())
    rows = marking.parse_import_file('supplier-page.pdf', source)
    with fitz.open(stream=rows[0]['label_pdf'], filetype='pdf') as label:
        print('ACTUAL_CROP_SIZE', tuple(label[0].rect), flush=True)
    return source
contract._framed_label_page = with_frame
raise SystemExit(pytest.main([
    '-n', '0', '-p', 'no:cacheprovider', '-q', '-s', '--tb=short',
    '-o', 'faulthandler_timeout=60',
    'tests/test_wms658_marking_import_contract.py::test_c22_audit_accepts_unchanged_label_cropped_from_supplier_page',
]))
PY
```

Ruff одного изменённого сервиса — PASS, mypy (`--cache-dir=/dev/null`) — PASS,
git diff --check — PASS. Diff frozen tests и requirements пуст. Зависимости,
широкие наборы, frontend/build и дочерние агенты не использовались.

Реальные исходный PDF и конечный print PDF/PNG инцидента 04.10 отсутствуют;
расследование R11 остаётся открытым. Этот synthetic PASS не доказывает инцидент.
Production/внешние API/секреты не использовались. Независимая перепроверка,
приёмка, CI и deploy этим исполнителем не выполнялись.
