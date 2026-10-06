# WMS-652 · совместимость ранее принятого legacy654 ledger

Actual provisional687 mergea5cf20 выявил backward-compatibility defect нового helper: legacy654 содержит `report`, но не `report_commit`; прежний exact-files format это позволял. Продукт/тест/реестр654 не меняются. После первоначальной незакоммиченной однострочной диагностики код восстановлен; formal до-code контракт отдельного tester1fb6646 импортирован06c1afde. На восстановленном коде реальный targeted RED: legacypositive1FAIL, newancillarymissingreportnegative1PASS. Wrong -k selectors/no-selected invocations не считаются RED.

Formal correction после frozenконтракта: обязательный immutable report_commit применяется к новой bounded ancillary687ветке; legacy exact-files сохраняет существующую metadata-проверку model/high/PASS. Ancillary без reportcommit по-прежнему отказана, продуктовые/чужие/семантические companions и удаление frozen tests запрещены.

Final6cases (четыре предыдущие687+два новых) PASS с настоящим JUnit,7subtests; CIproducer фильтр расширен ровно этими cases, old4IDs/report/exact сохранены, policy now1220caseIDs/233files/22suites. Полный actualdocgate после фикса ещё проверяется; независимое review pending. Provisional687C5 совместимости с684/586 не принята, P/S pending, main/etalon/deploy unchanged.
