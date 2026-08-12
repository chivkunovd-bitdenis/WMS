# TL-F002 — Любой читатель репозитория может выпустить APK с той же release-подписью

## Паспорт

- Finding ID: `TL-F002`
- Title — пользовательский результат, а не предполагаемая причина: складское устройство не может отличить официальную пилотную сборку от APK, собранного любым читателем репозитория
- Class: `SECURITY`
- Severity: P1
- Area / scenario ID: mobile release integrity
- First reviewer / independent verifier: teamlead / pending
- Environment and SHA: mobile Git object `09aa479fd8e311a8155c92074ab2f4a6ec843da4`
- Role / tenant / seller test IDs: N/A
- WB mode: N/A

## Ожидаемое поведение

- Источник правды, точный раздел или официальная ссылка: Android release signing is the identity used for APK update trust; repository review contract requires release/runtime provenance.
- Дата проверки внешнего источника: N/A
- Короткое ожидаемое поведение: private signing material and its unlock data are not reconstructible from the source repository.

## Фактическое поведение и воспроизведение

- Предусловия и физический контекст склада: read access to the tracked mobile Git history.
- Шаги от чистого состояния: inspect the pinned tree, build signing configuration, keystore metadata and file history without using the key.
- Что видно пользователю: nothing until a signature-equivalent APK is distributed; Android would treat the signer as the same pilot identity.
- Что произошло с данными, задачей, печатью или WB: no APK was signed and no external system was touched.
- Повторяемость: attempts / reproduced: static `1/1`.

## Доказательства

- screenshots: N/A
- sanitized request/response or trace ID: N/A
- DB/read-back proof: N/A
- relevant logs without secrets: keystore is a tracked `2680` byte PKCS12 container with one private-key entry; values are intentionally omitted.
- code path `file:line`: `android/app/build.gradle.kts:23-37` wires the tracked keystore and three tracked unlock literals into release; `android/README.md:41-49` documents the same arrangement (values omitted).
- existing automated test and its result: none found; no signing command was executed.
- Git history: blob introduced by `3ab29af9101403799c29118ec3b054a74da4bf0e` and remains reachable in history.

## Ущерб и граница

- Кто страдает и как часто: every device accepting updates under this pilot signing identity.
- Результат: утечка / неверная provenance: source access is sufficient to construct an APK indistinguishable by signer identity.
- Workaround and its cost: manually distribute verified APK hashes and uninstall/re-enroll devices when moving to a new signer.
- Почему это дефект, а не новая функция: release authenticity is an existing property of signed builds.
- Что точно не входит в эту находку: using, exporting, rotating or revoking the key; store signing; any credential value.

## Анализ причины

- Proven root cause / hypothesis / unknown: proven — signing material and unlock configuration are both tracked.
- Evidence separating cause from correlation: pinned Git tree and history contain all referenced inputs; key was never used during review.
- Retry, concurrency and recovery implications: signer replacement requires an explicit device migration because differently signed APKs cannot update in place.
- Tenant/seller/security implications: malicious code installed under the trusted signer could act with the operator's authenticated mobile session.

## Критерий закрытия без проектирования решения

- Given: a clean clone without external secret access
- When: release is built
- Then: it cannot produce the authorized production/pilot signer
- And: authorized CI/release retains reproducible artifact-to-commit provenance
- Negative: old repository history alone cannot create another trusted update

## Вердикт оркестратора

- Accepted / evidence missing / duplicate / conflict / out of scope: pending
- Second reproduction for P0/P1: static independent reproduction pending
- Queue status: proposed P1
