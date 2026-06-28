# Ревью CZ-модуля — рабочий журнал

> Живой документ. Каждый шаг ревью пишется сюда, чтобы не потерять прогресс при обрыве связи.
> Набор: `4e82c6b..HEAD`, 21 коммит `feat(cz)`, 125 файлов, +19248/−687.
> Сырые находки по измерениям — в `docs/_review_cz/find-<измерение>.md`.

## Статус
- [x] Шаг 1 — гейты (локально, оффлайн) — выполнено, есть находки (ниже).
- [x] Шаг 1b — pytest (через python3) — **45 passed** (marking-сабсет зелёный).
- [ ] Шаг 2 — многоагентное ревью 8 измерений (агенты пишут на диск).
- [ ] Шаг 3 — состязательная верификация находок.
- [ ] Шаг 4 — синтез финального отчёта.

---

## Шаг 1 — Гейты (ruff / mypy) — РЕАЛЬНЫЕ проблемы, CI будет красный

### ruff — 4 ошибки
- `tests/test_marking_reprint_defect.py:166` — `RUF059` распакованная `admin_h` не используется.
- `tests/test_marking_verify_pair.py:63` — `E501` строка длиннее 100.
- (+ ещё 2 в тех же тестах по тем же правилам.)
→ нефатально, но `ruff check .` не зелёный.

### mypy — 10 ошибок в 5 файлах
| Файл:строка | Ошибка | Оценка |
|---|---|---|
| `app/api/marking_codes.py:721` | `Item "str"/"None" of "str \| None" has no attribute "HTTP_404_NOT_FOUND"` | **подозрение на реальный баг**: `status` затёрт строковой переменной, обращение к `status.HTTP_404_*` упадёт в рантайме (AttributeError) на этой ветке |
| `app/api/marking_codes.py:940/942/989` | `UUID \| None` присваивается в `UUID` | возможное None-проглатывание, проверить |
| `app/services/marking_code_service.py:48` | `LAYOUT_BLOCK_CZ` не экспортируется явно | импорт/`__all__`, скорее стиль |
| `app/services/marking_code_service.py:1209` | несовместимые типы при переназначении `code_filter` | переменная `BinaryExpression` → `ColumnElement`, проверить |
| `app/services/marking_low_stock_service.py:81` | `STATUS_AVAILABLE` не экспортируется явно | импорт/`__all__` |
| тесты (2) | no-any-return / attr-defined | стиль/типизация |

### pytest
- **45 passed** за 35.8с (`python3 -m pytest`, marking+notification+print сабсет). Логика рабочая;
  красный CI сейчас только из-за ruff (4) и mypy (10) выше.

---

## Шаг 2 — Многоагентное ревью (в процессе)
8 измерений: инварианты/домен · конкурентность · миграции · мультитенант+authz · контракты API ·
безопасность кредов · фронт · тесты. Каждый агент пишет сырые находки в `docs/_review_cz/`.

**Готово 2/8 (на диске):**
- [x] `concurrency` → `find-concurrency.md` — 2×HIGH, 3×MEDIUM, 1 контр-находка.
- [x] `security_secrets` → `find-security_secrets.md` — 1×HIGH, 2×LOW.
- [ ] осталось 6: `invariants`, `migrations`, `tenancy_authz`, `api_contracts`, `frontend`, `tests`.

**Топ-находки пока (ship-blockers):**
- 🔴 Креды ЧЗ/СУЗ/МП при дефолтном конфиге шифруются ключом из публичного дефолтного
  `jwt_secret_key`, нет prod-гейта → дамп БД = открытые токены. (`integration_fernet.py:13-19`)
- 🔴 Выдача кодов из пула без `SKIP LOCKED` → ложный дефицit под параллелью. (`marking_code_service.py:1221`)
- 🔴 `print_all` не атомарен (commit на строку) → частично отпечатанные задания. (`:1278`+`:1536`)
- 🟠 mypy: `status` затёрт строковой переменной → AttributeError в рантайме. (`marking_codes.py:721`)
