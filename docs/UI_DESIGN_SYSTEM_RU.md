# UI: единый дизайн WMS

Источник правды для **новых и правимых** экранов. Конфликт с этим документом → исправлять UI, а не плодить исключения.

## Портал фулфилмента (FF) — `/app/ff/*`

**Обязательно:** [MUI](https://mui.com/) + тема приложения (`theme` в `frontend/src`).

| Использовать | Не использовать на FF-экранах |
|--------------|-------------------------------|
| `Paper`, `Table`, `TextField`, `Button`, `Alert`, `Stack`, `Typography` | Legacy `Card` / `Input` / `Button` из `frontend/src/ui/*` (тёмные `ui-card` ломают светлый shell) |
| `PageHeader` / заголовок как на `FfProductsCatalogScreen` | Отдельные тёмные «карточки» поверх светлого `AuthedAppLayout` |

**Эталон экрана:** `frontend/src/screens/v2/FfProductsCatalogScreen.tsx` — таблица в `Paper variant="outlined"`, фильтры/формы в `Paper`, ошибки в `Alert`.

**Навигация:** пункты в `AuthedAppLayout` (`data-testid="nav-*"`), маршруты под `/app/ff/...`.

**Формы:** `data-testid` на полях и submit; после `await` в submit — `const form = e.currentTarget` до await (Playwright / Strict Mode).

## Накладные (печать A4)

| Документ | Где кнопка |
|----------|------------|
| **Приёмка на ФФ** | Приёмка → документ → «Печать накладной» |
| Отгрузка на МП | Раздел **«Отгрузка»** → документ → «Печать накладной» |
| Operational outbound | Операции → отгрузки или документ из списка |

Этикетки коробов 58×40 — отдельная кнопка в блоке коробов, не накладная.

## Портал селлера — `/seller/*`

Отдельное приложение (`SellerApp`), тот же MUI-подход; публичный вход — `PublicAuthScreen` (MUI).

## Онбординг селлера (продукт)

1. Админ FF в разделе **«Селлеры»**: название бренда + **email**.
2. Бэкенд: `POST /sellers` → `POST /auth/seller-accounts` **без пароля** → случайный hash + `must_set_password=true`.
3. Админ передаёт селлеру **только email** и URL портала селлера.
4. Первый вход: email + **пустой пароль** → экран «Задать пароль» → `POST /auth/set-initial-password`.

Пароль в ответ API **не отдаётся** (только сценарий «селлер задаёт сам»).

## Чеклист перед merge UI

- [ ] Экран FF на MUI, без `ui-card` в основной области
- [ ] Есть `data-testid` для e2e
- [ ] `npm run build` в `frontend/`
- [ ] При смене пользовательского пути — Playwright по `AGENTS.md`
