# Release review manifest

> Копия для нового прогона: сохрани как `04_release_manifest.md`.
> Заполняется агентом `release-implementation-reviewer` на `phase=init`.
> На `phase=batch` карточки **не сжимать** — batch читает их целиком.

```yaml
phase: init          # init | batch | final | done
batch_size: 2
artifacts:
  - docs/analysis/01_normalized_process_spec.md
  - docs/analysis/02_technical_builder_plan.md
  - docs/analysis/03_builder_plan_review.md
fallback:
  - docs/MVP_DECISIONS_RU.md
  - docs/IMPLEMENTED_PRODUCT_SCENARIOS_EN.md
report: docs/analysis/04_release_implementation_review.md
```

## Таблица сценариев

| id | title | status | verdict | batch | notes |
|----|-------|--------|---------|-------|-------|
| S01 | … | pending | — | — | |
| S02 | … | pending | — | — | |

`status`: `pending` | `in_progress` | `done`  
`verdict`: `works` | `partial` | `broken` | `не подтверждено` | `—`

---

## Карточки сценариев

### S01 — {короткое название}

**Потребность пользователя (зачем пришёл):**
…

**Успех для пользователя (не для системы):**
…

**Границы сценария:**
- Входит: …
- Не входит: …

**Обязательный путь (шаги пользователя):**
1. …

**Обязательные данные / действия / статусы на пути:**
- …

**Типичные продуктовые риски:**
- …

**Критерий «не готово» (продуктово):**
- …

**Ссылки на артефакты:**
- 01: … | 02: … | 03: … | TC: …

**Ожидаемые точки в коде (для batch):**
- frontend: …
- backend: …

---

### S02 — …

(повторить шаблон для каждого сценария)

---

## Журнал батчей (агент дописывает)

| batch | date | scenarios | outcome |
|-------|------|-----------|---------|
| 1 | | S01, S02 | |
