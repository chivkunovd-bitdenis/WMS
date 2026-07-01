---
name: railway-staging-deploy
description: >-
  Выкатка на Railway staging по упрощённым правилам: push в ветку staging,
  без prod. Используй при «лей на railway», «deploy staging», «выкати на
  railway», «посмотреть на staging».
---

# Railway staging deploy (WMS)

## Жёсткие правила

1. **Prod не трогать:** не менять `deploy.yml`, `docker-compose.prod.yml`, `scripts/deploy/prod-update.sh`, prod env на VPS.
2. Staging = только ветка **`staging`** + Railway (см. `docs/analysis/RAILWAY_STAGING_RU.md`).
3. Перед выкаткой — **закоммитить** все изменения задачи.

## Когда пользователь просит «лей на railway»

1. Прочитать `docs/analysis/RAILWAY_STAGING_RU.md` при сомнениях по env/ветке.
2. Убедиться, что рабочее дерево чистое (`git status`).
3. Выполнить из корня репозитория:

```bash
./scripts/railway-staging-deploy.sh
```

4. Сообщить пользователю:
   - что ушло в `origin/staging`;
   - что Railway пересоберёт только сервисы с изменениями в `backend/**` или `frontend/**`;
   - ориентир по времени 2–6 мин;
   - напомнить закладку staging URL и фиксированный логин из Railway env (не локальные порты).

5. Опционально smoke, если известен URL:

```bash
WMS_STAGING_URL=https://….up.railway.app ./scripts/railway-staging-smoke.sh
```

## Что НЕ делать

- Не пушить в `main` «чтобы задеплоилось на railway» — Railway слушает `staging`.
- Не запускать prod deploy / SSH / `prod-update.sh`.
- Не требовать локальный `docker compose` или `npm run dev` для просмотра правок — пользователь смотрит staging URL.
- Не ждать полный Playwright e2e перед staging — на push в `staging` e2e в CI не гоняется.

## Полный CI перед prod

PR → `main`: ruff, mypy, pytest, Playwright. Prod деплой только после зелёного CI на `main`.
