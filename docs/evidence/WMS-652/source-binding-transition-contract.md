# WMS-652: контракт перехода fixed product SOURCE

Этот тестовый контракт подготовлен по
`docs/evidence/WMS-652/night1007-integration/CI-DELTA.md` из integration
worktree на `f71b99c0f19bdbf48e8e0b95b62aefe8709307fc`. Тот документ описывает
будущий общий SOURCE, но не является независимой приёмкой product-reference.

Пока `final_reviewed_source` в fixture равен `null`, действующий и единственный
допустимый trusted reference — `d61805978b3e7878d1056c99b4e6e0823edf49a5`.
Контракт сохраняет существующий case ID
`ReleaseCommandContracts.test_actual_candidate_product_scope_uses_fixed_independently_reviewed_reference`
и запрещает замену на `HEAD`, `${GITHUB_SHA}` или current unreviewed integration
candidate. В workflow нет нового placeholder, environment lookup или dummy command.

После независимой приёмки и freeze интегратор обязан в одном проверяемом изменении
внести фактический lowercase 40-hex SHA в `final_reviewed_source`, добавить его в
`accepted_reviewed_sources` и заменить literal pin той же командой workflow.
До этого момента SHA намеренно не подставляется и не угадывается.
