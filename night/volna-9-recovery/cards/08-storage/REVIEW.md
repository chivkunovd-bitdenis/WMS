# Ревью · 08-storage · повторная проверка ремонта

Вердикт: CHANGES_REQUESTED.

ВЕРДИКТ: НАХОДКИ 1

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts:113` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts:114` — обязательный ремонт первой находки жёстко считает прошлым месяцем июль 2026 года, хотя экран в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx:38` вычисляет прошлый месяц от текущей даты. Начиная с 1 сентября 2026 года экран откроет август, проверка `toHaveValue('2026-07')` упадёт до сохранения тарифа и повторного GET; сценарий перестанет доказывать исходную финансовую регрессию и будет краснить обязательный Playwright-гейт по календарю, а не по поведению продукта. Цена: находка о ложном `tariff_configured=true` для прошлого месяца остаётся закрытой только до конца августа и не получает постоянной регрессионной защиты.

## Проверено и нормально

- Замороженный чек-лист предыдущего `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/REVIEW.md` проверен по всем трём пунктам на ремонтном diff `878f62dd4b5d322a2ad2d28e89b96d0d2d34faab..05f85191155d922eaf13d90086002ebdbac4ac4d`: фикстуры минимальной ставки и прошлой даты теперь отдают пустые строки, видимая кнопка открывает настоящий диалог, и обе проверки доходят до недоступной кнопки с объяснением.
- Новый сценарий сохранения поздней ставки действительно подписывается на POST и повторный GET до клика, требует ровно одно чтение после POST, отвергает строки из ответа POST и проверяет видимые «Тариф хранения ещё не задан» и «Задать тариф». Кроме календарной привязки выше, логика сценария соответствует фиче 2.
- Трассировка ремонта согласована: `S-11-TC-018` остался только за отрицательным восстановленным остатком и отсутствием частичного ledger-начисления, а ретроактивная московская дата получила единственный номер `S-11-TC-021` в тесте, каталоге кейсов и артефакте карточки. Продуктовый ремонт ограничен разрешённым `frontend/tests-e2e/storage.spec.ts`; `tests/cases/` и `night/` рассмотрены как стадийные артефакты.
- Локально прошли `npx tsc --noEmit -p tsconfig.app.json`, `npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` (`6 passed`), список трёх целевых Playwright-сценариев и `git diff --check`. Исполнение Playwright остановлено средой до тестов: webServer не получил право слушать `127.0.0.1:18000`; production, Wildberries и кабинеты учётных данных не использовались. Артефакт записан в назначенный файл, но не сохранён коммитом: песочница запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).
