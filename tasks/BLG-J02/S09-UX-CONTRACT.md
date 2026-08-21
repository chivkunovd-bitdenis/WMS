# S09 UX_CONTRACT_AND_MOCKUPS - BLG-J02

## Source and operator outcome

Backlog item `BLG-J02` replaces the technical response detail `invalid_token`.
It is returned when the saved authentication token can no longer be decoded, so
the operator is already signed out before the login form is shown. The current
message exposes that implementation detail and can be confused with a
Wildberries credential problem.

For both the fulfillment and seller portals, the operator must instead see
`Сессия завершилась. Войдите снова, чтобы продолжить работу.` The existing
login form remains the next action. Once login and profile verification succeed,
the operator returns to the same safe working route when it is still available;
otherwise they land on that portal's ordinary start screen. No work is replayed
and no credentials are changed by this flow.

## Scope and trigger

- This contract applies only when the active WMS session is rejected with the
  authentication condition represented by `invalid_token` while loading the
  current profile.
- It covers the fulfillment portal and the `/seller` portal because they share
  the same session hook and public login surface.
- A bad email/password on the login form, a portal-role mismatch, a network
  failure, an authorization denial, and errors from an already loaded working
  screen retain their separately defined messages and handling.

## UI-kit mapping by zone

| Zone | Component and required use |
| --- | --- |
| Login-page frame | `ScreenShell` with the existing `ScreenHeader`; BLG-J02 creates no new page, sidebar, table, tab, or workspace section. |
| Session-expired notice | `ErrorNotice` displays the exact human message. It must never render `invalid_token`, HTTP status text, token contents, or Wildberries-key wording. |
| Login form | Existing login form uses `TextInput` for email and password. Its primary submit command is `PrimaryAction` with `Войти`. The normal disabled/busy state prevents a second submission. |
| Return feedback | `ErrorNotice` is reused only when a successful authentication cannot restore the saved route. It explains the fallback without exposing route validation internals. |
| Actions | `PrimaryAction` is the login submit action. `SecondaryAction`, `DangerAction`, `ActionMenu`, and `ModalDialog` are not needed and must not be added. |
| Table, statuses, filters, tabs and scanner zone | `DataTable`, `StatusChip`, `FilterBar`, `TabsBar`, and `ScannerLine` are not touched. The session interruption must not add a banner, row status, or scanner control to a working screen. |

All visible elements in the changed zone use components exported by
`frontend/src/ui-kit/index.ts`. No missing component is required, therefore
there is no `DESIGN_SYSTEM_GAP` blocker.

## Safe return contract

1. When the profile check identifies `invalid_token`, the application clears
   the invalid local session and records the current route as a pending return
   target before displaying the public login form.
2. A pending return target contains only the current portal-relative pathname,
   query, and hash. It is application state for this login attempt; it is not
   shown to the operator and must not contain a token, password, or API error.
3. Before navigation after login, the target must be accepted only when it is
   an internal route of the same portal. Absolute URLs, protocol-relative URLs,
   a different portal base, an empty value, and an unrecognised route are
   rejected. The target is never passed to an external redirect.
4. The application restores the target only after a login response has supplied
   a new session and the profile check has confirmed that the user belongs to
   the current portal. The redirect is a replacement navigation so browser Back
   does not reopen the expired-session state.
5. If the saved route is invalid, no longer exists, or is unavailable to the
   signed-in role, the application sends the operator to the established start
   route: the fulfillment portal start screen or seller `/documents`. It shows
   `Вход выполнен. Открыт доступный рабочий экран.` The fallback is not an
   authentication failure and must not sign the operator out again.
6. The return target is consumed after either successful restoration or safe
   fallback. Cancelling, failed login, or a network failure leaves the login
   form in place and does not navigate or replay the interrupted request.

## Textual mockups and required states

### A. Expired session on a working route

```text
ScreenShell
  ScreenHeader: "Вход в WMS" | "Вход в портал селлера"
  ErrorNotice
    "Сессия завершилась. Войдите снова, чтобы продолжить работу."
  Login form
    TextInput: "Email"
    TextInput: "Пароль"
    PrimaryAction: "Войти"
```

The expired working screen is replaced by the public login surface. The notice
does not identify the marketplace or ask the operator to edit any key.

### B. Successful login with restored route

```text
PrimaryAction: "Войти" [busy]
  -> profile verified for the current portal
  -> replace navigation to the saved internal route
```

The original screen may reload its normal data, but the interrupted request is
not automatically retried. A route-level loading state, if already present, is
allowed; no additional session-specific loader is introduced by this card.

### C. Successful login with safe fallback

```text
ErrorNotice
  "Вход выполнен. Открыт доступный рабочий экран."
```

This notice is shown on the portal start screen only when a saved target was
rejected or cannot be opened for the confirmed role. It gives no URL or access
rule detail.

### D. Login cannot complete

```text
ErrorNotice: existing login-specific message
TextInput: "Email" [entered value retained where the existing form permits]
TextInput: "Пароль"
PrimaryAction: "Войти" [available after the request ends]
```

For invalid credentials, password setup, network failure, and portal mismatch,
the existing respective message remains authoritative. The pending return is
not used until an eligible, verified login succeeds.

### E. Repeated expiry or unavailable return

```text
ErrorNotice
  "Сессия завершилась. Войдите снова, чтобы продолжить работу."
Login form
```

If the newly issued session is again rejected, the application clears it and
returns to the same login surface without a redirect loop, duplicate message,
or attempt to reopen the old request. If route access is lost after login, the
safe fallback in state C is used.

## Review and case handoff

- S10 checks that the notice is clearly distinct from an invalid password,
  portal-role mismatch, or marketplace integration issue; it must remain
  readable on a narrow warehouse workstation without pushing the login command
  below the usable viewport.
- S10 checks the absence of an extra modal, banner, table status, or scanner
  interruption on operator screens.
- S11 confirms the fallback start routes and that losing route access after
  re-login should fall back rather than produce an authorization leak.
- S15 must cover fulfillment and seller routes; valid same-portal return;
  query/hash preservation; external/protocol-relative/cross-portal/unknown
  return rejection; no duplicate login submission; failed login retaining the
  form; second expiry; role mismatch; and no replay of the interrupted mutation.

## Out of scope

No implementation, API contract change, token lifetime change, credential or
secret operation, external marketplace call, worker change, deploy, or live
browser acceptance is part of S09.

## S09 verdict

`UX_CONTRACT_READY`: the visible states and safe internal return behaviour are
specific enough for S10 Design Review and S11 Product Contract Approval, and
they use only existing UI-kit components.
