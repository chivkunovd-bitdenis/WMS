# Наряд · 20260827-vladelec-27-08-2026-ispravit-obschiy-ui-

**Полоса:** обычная
**Тип:** экран
**Заведён:** 27.08.2026 10:22

## Просили дословно

> Владелец 27.08.2026: исправить общий ui-kit shrink label для native SelectInput и MoscowDateTimeInput на S-19 без screen workaround

## Экраны

- `S-19` /app/ff/settings — FfSettingsScreen

## Границы правки

Разрешено трогать только эти файлы:

- `frontend/src/screens/ff/FfSettingsScreen.tsx`
- `frontend/src/ui-kit/FormFields.test.tsx`
- `frontend/src/ui-kit/FormFields.tsx`
- `frontend/src/ui-kit/UiKitShowcase.tsx`
- `frontend/src/utils/ffPermissions.ts`
- `frontend/src/utils/separateMarkingPrint.ts`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260827-vladelec-27-08-2026-ispravit-obschiy-ui-/`
- [ ] влито
