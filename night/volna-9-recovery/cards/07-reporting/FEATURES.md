ФИЧ: 1

## Фичи

### 1. Собрать переходы пагинации отчёта в единый ActionGroup

Оператор под таблицей «Остатки и движения» видит переходы «Назад» и «Вперёд» как одну согласованную группу одинакового размера, а не как две случайно различающиеся второстепенные кнопки. Доступность переходов, их подписи, серверная пагинация и верхние агрегаты остаются без изменений. Это закрывает обе ещё не принятые находки DESIGN REVIEW: R-31 о самостоятельных второстепенных действиях и R-32 о разной ширине кнопок. Новый ui-kit не создаётся: подходящий `ActionGroup` уже есть.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`

Зависимости: нет.

Проверка: открыть `/app/ff/reports`, получить больше 50 строк и убедиться, что строка пагинации показывает общий контрол «Назад»/«Вперёд» с одинаковыми габаритами; на первой странице «Назад» недоступна, «Вперёд» открывает вторую страницу, меняет таблицу и не меняет верхние показатели. E2E-сценарий с `TC-NEW-F07-013` проверяет эти видимые состояния и равную ширину двух кнопок через их bounding box.

## Порядок

1. Выполнить фичу 1 одним frontend-исполнителем: она самостоятельна, опирается на уже принятый `ActionGroup` и не требует backend-работы.

Параллельных фич в этом перепланировании нет.

## Что осталось за бортом

- Уже принятые данные, API, ui-kit, экран, маршруты и seller-исправления не возвращаются в разработку: это перепланирование ограничено двумя незакрытыми находками из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DESIGN-REVIEW.md`.
- Нового reusable ui-kit-контрола нет: существующий `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/Actions.tsx` уже содержит `ActionGroup`, который закрывает R-31 и R-32.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
