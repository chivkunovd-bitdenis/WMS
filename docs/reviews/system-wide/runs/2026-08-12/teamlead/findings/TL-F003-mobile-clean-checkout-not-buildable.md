# TL-F003 — Чистый mobile checkout не содержит исходники API-клиента, от которых зависит приложение

## Паспорт

- Finding ID: `TL-F003`
- Title: pinned mobile source cannot be compiled from a clean checkout without recreating ignored code from an unpinned source
- Class: `RELIABILITY`
- Severity: P1
- Area / scenario ID: mobile build/runtime alignment
- First reviewer / independent verifier: teamlead / pending
- Environment and SHA: mobile `09aa479f`
- Role / tenant / seller test IDs: N/A
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: `android/README.md` declares the build command and generated API client.
- Короткое ожидаемое поведение: a pinned clean checkout has a deterministic, build-integrated way to produce every source dependency from the pinned contract.

## Фактическое поведение и воспроизведение

- Предусловия: inspect only the pinned Git tree, ignoring shared-checkout untracked files.
- Шаги: list tracked main sources → find generated-package imports → list tracked generated directory and build tasks.
- Что видно пользователю: N/A; build/release reproducibility failure.
- Что произошло: 14 tracked source files import `ru.wms.tsd.core.api.generated`; zero generated source files are tracked; `.gitignore` excludes the directory. Generation is a separate script that selects a live local backend before a fallback and is not a Gradle dependency.
- Повторяемость: static `1/1`; local functional build prohibited.

## Доказательства

- code path: `.gitignore:5`; `android/README.md:31-39`; imports begin at `android/app/src/main/java/ru/wms/tsd/core/api/ApiProvider.kt:5`.
- existing automated test and its result: seven tracked test files exist, but they cannot establish a clean source build; not run by scope.

## Ущерб и граница

- Кто страдает: CI/release engineers and incident recovery.
- Результат: unreproducible build and possible API-contract drift depending on whichever backend answers locally.
- Workaround: preserve dirty generated files or manually generate them; both break commit-level reproducibility.
- Почему дефект: README promises a normal build from the repository.
- Не входит: choosing a generator technology or committing generated code.

## Анализ причины

- Proven root cause: generated compilation inputs are neither tracked nor wired deterministically into the build.
- Retry/concurrency/recovery: a recovery build can silently use a different API schema.
- Tenant/seller implications: contract drift can misroute operator actions, though no such runtime effect was exercised.

## Критерий закрытия

- Given: a clean checkout at a named SHA with no local backend
- When: documented test and release builds run
- Then: generated client comes from a pinned schema/toolchain and compilation succeeds
- And: generation cannot silently bind to another running project

## Вердикт оркестратора

- Accepted: accepted by orchestrator as P1 build/reproducibility finding
- Second reproduction for P0/P1: clean CI reproduction required
- Queue status: accepted P1
