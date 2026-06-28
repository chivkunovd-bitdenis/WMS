---
name: release-implementation-review
description: >-
  Запускает release-implementation-reviewer: продуктовый аудит реализации перед
  релизом по docs/analysis/01–03, батчами по 2 сценария, отчёт в
  04_release_implementation_review.md. Слова: «релизное ревью», «release review»,
  «04_release», «проверь реализацию перед релизом», «продуктовый аудит».
disable-model-invocation: true
---

# Release Implementation Review

**Не пиши код.** Запусти агента **`release-implementation-reviewer`** (`~/.cursor/agents/release-implementation-reviewer.md`).

**Не путать** с `adversarial-reviewer` (ревью diff PR).

## Команды владельца

```text
release review phase=init
release review phase=batch
release review phase=final
```

Повторяй `phase=batch`, пока в manifest не `phase: final` или `done`.

## Артефакты

| Файл | Роль |
|------|------|
| `docs/analysis/01_normalized_process_spec.md` | Процесс, потребности (init) |
| `docs/analysis/02_technical_builder_plan.md` | Экраны, API (init) |
| `docs/analysis/03_builder_plan_review.md` | Риски плана (init) |
| `docs/analysis/04_release_manifest.md` | Карточки + прогресс |
| `docs/analysis/04_release_implementation_review.md` | Итоговый отчёт |

Шаблоны: `04_release_manifest.template.md`, `04_release_implementation_review.template.md`.

## Цикл

1. **init** — карточки продуктовой логики из 01–03 (7–10 сценариев)
2. **batch** × N — по 2 сценария: продуктовый допрос + UI→API→backend
3. **final** — вердикт релиза, блокеры, сквозные проблемы

Подробный протокол — только в файле агента.
