# 02-verdikt-screen — browser acceptance

Проверяемый product HEAD до browser-test repair: `50cc5ed668a77ef962a1fddd57f1f48891a9d472`.

Test-only repair: `04ff7b45`.

## Scope

- существующий S-03, только зона вердикта WB в строке ЧЗ и действующий серверный гейт передачи;
- 0 новых экранов;
- 0 новых колонок;
- 0 новых контролов;
- S-14 и S-15 проверяются только как соседняя регрессия.

## Targeted checks

- S-03-TC-014: PASS — принятый WB-код показан чипом, строка не окрашивается зелёным;
- S-03-TC-018: PASS — скрытая вкладка не может передать поставку по устаревшему положительному вердикту;
- S-03-TC-016 backend concurrency/stale-result set: `3 passed`;
- ESLint изменённого Playwright spec: PASS;
- `git diff --check`: PASS;
- local Docker stand: API `/health` — `ok`, FF web — HTTP 200.

Два старых browser-test blocker были исправлены без изменения продукта: ввод теперь направлен во вложенный textbox существующего MUI TextField, а проверки чипа и кнопки выполняются на тех штатных вкладках, где эти элементы реально находятся.

## UI invariants

- S-14: PASS, нарушений 0;
- S-15: PASS, нарушений 0;
- standalone MOCKUP.html: PASS, нарушений 0;
- S-03: единственный ранее существовавший R-32 (`34/40` высоты кнопок). Product code карточки browser-repair не меняет, поэтому это не регрессия 02 и не основание расширять scope.

## Screenshots

- `mockup-s03-verdict.png`;
- `s03-fbs-live.png`;
- `s14-packaging-live.png`;
- `s15-pending-marking-live.png`.

## Live browser judge

Вердикт: PASS.

На local stand вручную открыты и сверены S-03, S-14 и S-15, а также сохранённый standalone `MOCKUP.html`. Экраны штатные; новых экранов, колонок и контролов нет. Макет ограничен существующей зоной ЧЗ и не меняет соседние зоны.
