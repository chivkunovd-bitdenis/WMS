# Наряд: кеш корневого FF

Полоса: аварийная

Просьба владельца дословно: «На Windows система не работает, на маке работает».

Экран: общий вход FF, без изменения состава или дизайна экранов.

## Контракт

- Корневой SPA URL `/` получает тот же `Cache-Control: no-cache, no-store, must-revalidate`, который уже настроен для `/index.html`.
- API, ассеты, seller portal, экраны и бизнес-логика не меняются.

## Разрешённые файлы

- `frontend/deploy/Caddyfile`
- `deploy/Caddyfile.http`
- `tasks/20260824-kesh-kornevogo-ff/NARYAD.md`
