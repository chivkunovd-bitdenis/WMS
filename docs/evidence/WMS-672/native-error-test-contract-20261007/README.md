# WMS-672: дополнительный контракт до нативного исправления

Отдельная замещающая тестовая роль Sol6.1. Источник:
`ecb1d5721ea823a0ffd861303302c4b8dc731e6d`; ветка
`codex/wms672-native-error-contract-20261007` в существующей постоянной worktree.
Прочитаны origin/etalon AGENTS, test-writer skill, R1–R7/C1–C12/коррекция расписания
WMS-672, все11 прежних browser cases и неизменный C5 с отказами150/299.
Разработчик отдельно согласовал два будущих product paths и ждал этот контракт
до начала реализации. Эта сессия не принимает собственную новую дельту.

Основание — реальный Linux141 diagnostic9d90d8e5, run37527056184. На повторе
после injected150 декодер отверг валидный PNG227; тот же iframe EncodingError
дошёл до catch, но потерял сообщение из-за parent `instanceof Error`.
Конкретная причина внутреннего ресурса Chromium не установлена. Proposed32→16
остаётся технической гипотезой; ни16, ни другая цифра не превращаются в контракт.
Существующий frozen browser C5 уже является RED до кода для этой Linux проблемы.

## Новый исполнимый контракт

Команда из корня:

```sh
node --test --test-reporter=tap frontend/tests-e2e/wms672-native-errors.test.mjs
```

Планируемый отдельный raw report в CI: `release-print/672-native-errors.tap`;
точные7 TAP names и source closure приведены в `contract.json`.
CI wiring/registry/приёмка принадлежат интегратору и независимой роли.
Старый `release-print/672.json` и все11 его случаев остаются точными и прежними.

Тест исполняет настоящий `printBarcodeLabel.ts` и неизменённую функцию
`printInboundInternalLabels` из `FfInboundRequestView.tsx`: TypeScript AST выбирает
её initializer по имени, transpile исполняет полный исходный body без переписывания
catch. Не извлекается придуманная нормализация и не подменяется операция печати.
Функция исполняется в родительском jsdom realm с настоящим print utility;
iframe имеет отдельные Error/DOMException constructors. Изменение только catch
expression не ломает извлечение. Полный React/MUI экран/его layout здесь не рендерится.

Управляемые границы: HTTP/storage callbacks, генерация небольшого синтетического
PNG, decode/print как платформенные действия jsdom. Actual Chromium/native image
readiness не объявляется выполненной: jsdom не имеет нативного PNG-декодера.
Ошибка — настоящий `new iframe.DOMException(reason, 'EncodingError')`, который
является iframe Error и не является parent Error. Приём/возврат/качество CODE128/
PDF продолжают проверять прежние browser contracts, а не эти маленькие PNG.

Семь случаев:

- Отказы150/299 на валидном синтетическом source и150 на заведомо invalid data URL:
  сохранить точное доступное сообщение, снять busy/reentrancy, убрать iframe,
  ноль передач/отметок/успешных attempts. Assertions отсутствия внешних действий
  выполняются перед целевым message assertion и подтверждены уже на RED source.
- Пустое/нестроковое/отсутствующее сообщение: прежний generic fallback,
  снятый busy и ноль внешних действий.
- 300 held readiness calls: фактическое перекрытие не менее двух, ноль transfer/
  marks/source-save пока подготовка не завершена; после release все300 готовы
  до сохранения source и единственной передачи, точный исходный порядок300,
  ровно300 отметок, complete и живой iframe до afterprint.

**До product code:3 содержательных FAIL,4 PASS,0 skip/cancel.** Все три FAIL —
точное `screen must retain available native error reason`: исходный catch
подставляет generic вместо `The source image cannot be decoded.`. Это реальные
assertion failures на прочитанном source, не import/setup/collection errors.
Raw TAP сохранён в `precode-red.tap`; `node --check` и `git diff --check` PASS.

Проверено равенство всех прежних browser/DOM/Vite files базовому source.
Исходный C5, его150/299, retries, assertions и timeout не менялись. Product,
CI, policy, требования и общая release worktree не редактировались. Нового
широкого браузерного запуска, Linux dispatch, printer/production не было.

После реализации нужны этот неизменный7-case GREEN, отдельное независимое ревью
и один согласованный actual Linux141 запуск прежнего C5 на точном product SHA.
Он определит, сработала ли гипотеза меньшего окна. Message preservation само
по себе не исправляет retry bulk decode и не является доказательством выпуска.
