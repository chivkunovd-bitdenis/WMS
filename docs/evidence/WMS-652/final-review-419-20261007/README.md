# Независимые адресные доказательства 419 + инкремент b6

Runtime fixture был detached Git worktree на `4190460c97db0db439712b17a083c5b474ee3d74`, с symlink на существующие frontend/node_modules. Никакие зависимости не устанавливались. Финальный объект — `b6c2140d85e7ca5f8b7ede1cb26d30b1744c55a6`; P — `98978e667bbc305cc08a9b541016fef06686388e`. Runtime проверки 419 сохранены, аннотация b6 проверена отдельно без повторения браузера.

`replay_r2.cjs`/`r2-replay.json` сравнивают реальные immutable helpers 4ed/419 на исходном PDF XML предыдущего независимого FAIL (121.769526 pt) и опубликованных отрицательных/положительных fixtures. Используется собственный исторический артефакт, а не перегенерированный вместо контрпримера PDF.

В frontend fixture последовательно выполнены:

```sh
WMS_PRINT_CHROMIUM=/Users/deniscivkunov/Projects/WMS/.worktrees/night1007-679-680/.agent-runs/wms680-chrome-cli.mjs node node_modules/vitest/vitest.mjs run src/utils/wms680PrintGeometry.test.ts --pool=forks --maxWorkers=1 --no-file-parallelism --reporter=json --outputFile=../../docs/evidence/WMS-652/final-review-419-20261007/geometry.json
WMS_PRINT_CHROMIUM=/Users/deniscivkunov/Projects/WMS/.worktrees/night1007-679-680/.agent-runs/wms680-chrome-cli.mjs node node_modules/vitest/vitest.mjs run src/utils/wms680PrintGeometry.test.ts -t 'marketplace_unload сохраняет' --pool=forks --maxWorkers=1 --no-file-parallelism --reporter=json --outputFile=../../docs/evidence/WMS-652/final-review-419-20261007/geometry-retry.json
node node_modules/vitest/vitest.mjs run src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx --pool=forks --maxWorkers=1 --no-file-parallelism --reporter=json --outputFile=../../docs/evidence/WMS-652/final-review-419-20261007/inbound684.json
```

Сырые JSON/log сохранены: geometry сначала 12 PASS/1 FAIL, адресный повтор 1 PASS/12 filtered; inbound684 13 PASS/0 skip. Первый DOM timing symptom не скрыт и не заменён чистым повтором всего набора. Это реальный Chrome через существующий CDP adapter, а не синтетический PDF-парсер.

`audit.py`/`audit.json` — завершённый аудит immutable 419: все hashes, сохранность SOURCE0151 1146/18 bindings, реальные PG658 XML и шесть независимых отрицательных мутаций через действующий parser, настоящий workflow producer/needs, точные двухшаговые Git blob edges и derivation activation ledger. Скопированный `pg658.xml` — опубликованное исполнителем настоящее PG evidence; reviewer проверил его и негативные мутации, не запускал PG заново. Published aggregate replay metadata прочитаны, весь 4777-case replay здесь не воспроизводился.

`680-template.json` идентичен 419 и b6. `P-S-template.json` относится к исходному P0b5c/419; его нельзя использовать как финальный pin. **`P-S-template-b6.json` — финальный одобренный P989.** `incremental-b6.cjs`/JSON проверяют единственную аннотацию типа, фактическую TypeScript компиляцию и совпадающий JS digest, точный список четырёх новых путей, единственный policy hash refresh и обновление только P полей шаблона. Старый audit 419 сохранён без переписывания истории.

Все скрипты читают проверяемый исходный код через Git SHA. Результат PASS относится к ограниченному независимому отчёту; post-activation tests, strict gates и новый полный remote CI требуют отдельного фактического исполнения.
