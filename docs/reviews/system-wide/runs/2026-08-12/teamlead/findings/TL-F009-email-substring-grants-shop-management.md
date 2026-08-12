# TL-F009 — Подстрока в email выдаёт селлеру управление чужими магазинами tenant

## Паспорт

- Finding ID: `TL-F009`
- Title: a regular seller becomes a shop manager solely because a hard-coded personal-name marker appears anywhere in the email
- Class: `SECURITY`
- Severity: P1
- Area / scenario ID: seller authorization / delegated shops
- First reviewer / independent verifier: teamlead / unit contract confirms behavior
- Environment and SHA: `a39530c`
- Role / tenant / seller test IDs: static synthetic users only
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: persisted `users.can_manage_seller_shops`, explicit delegation records, and tenant/seller isolation contract.
- Короткое ожидаемое поведение: cross-shop authority is granted by an explicit stored permission, not identity text.

## Фактическое поведение и воспроизведение

- Preconditions: fulfillment seller with a seller_id and an email containing one of six hard-coded markers.
- Steps: authenticate → `/auth/me` lists delegatable shops → PUT `/auth/seller-shops` enables delegation → use effective seller switching.
- User/data effect: seller can select other non-test shops in the same tenant and access product/self-service paths under the effective seller.
- Repeatability: static `1/1`; parametrized unit contract has five positive examples.

## Доказательства

- code path: `seller_shop_service.py:24-58` returns true on substring before checking configured allowlist; `api/auth.py:291-344` exposes list and PUT; `api/deps.py:39-50` accepts effective seller only for this predicate; product routes consume it.
- existing test: `backend/tests/test_seller_shop_allowlist.py:24-35` codifies marker-based allow; not rerun due scope.

## Ущерб и граница

- Кто страдает: other sellers in the same tenant when an unrelated account's email happens to match a marker.
- Результат: unauthorized cross-seller visibility/mutation inside a tenant.
- Workaround: avoid marker substrings and audit accounts manually; this is not enforceable as authorization.
- Почему дефект: authorization derives from mutable identifier text instead of permission state.
- Не входит: intentionally configured DB flag, explicit environment allowlist, or cross-tenant access (not shown).

## Анализ причины

- Proven root cause: hard-coded substring allowlist in production service path.
- Retry/recovery: authorization persists as long as the email matches; removing delegations does not remove manager capability.
- Tenant/seller implications: tenant boundary remains, seller boundary is bypassed.

## Критерий закрытия

- Given: a regular seller whose email contains any name/marker but whose explicit permission is false
- When: it reads/updates seller shops or supplies an effective seller
- Then: access is denied
- And: explicit manager grant works and remains tenant-scoped

## Вердикт оркестратора

- Accepted: accepted by orchestrator as P1 static same-tenant cross-seller authorization finding
- Second reproduction for P0/P1: disposable-tenant runtime negative test required
- Queue status: accepted P1; runtime closure still required
