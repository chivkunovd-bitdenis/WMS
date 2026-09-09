# WMS-395 release: public production Chrome smoke, 9 September 2026

Result: **PUBLIC_UI_PASS** after root verified production deployment
`743a794bf0ee9e20cccf7f87c05138b035604ec9`. Root's deployment verification is separate
from this browser check; this script records that supplied SHA and inspects the real
public production UI. It does not independently infer a backend commit from a login page.

Headless installed Google Chrome used a fresh context with no authentication token,
cookies or saved browser session. The staging token was not read or sent to production.
The guard permitted only GET/HEAD/OPTIONS; all other request methods would have been
blocked. No such blocked requests occurred.

Observed and visually inspected:

- `/app/ff/fbs` returned200 and displayed the FF login form with Email, Password and
  "Войти". The protected FBS workspace was not visible or operated.
- `/seller` redirected302 to `/seller/`, which returned200 and displayed the distinct
  seller login form and portal heading.
- On both forms, the actual "Забыли пароль?" control was clicked. Production renders it
  as a `type=button` navigation control rather than an anchor. Both clicks displayed
  "Восстановление пароля", the empty Email field, "Прислать ссылку" and "Назад ко входу".
  No values were entered and the recovery form was not submitted.

Final run:158 same-origin response records; all returned200 except the expected seller
redirect302. Unhandled JavaScript errors:0. Blocked mutation attempts:0. Chrome closed
in finally. Screenshots and safe HTTP path/status records are in
`production-public-smoke-20260909/`; no tokens, credentials or request headers are stored.

The initial smoke visited only the two login forms because its link discovery looked for
anchors. After inspecting their screenshots and observed button labels, the QA script was
extended to click the actual non-submit recovery buttons and the public check was repeated.
No application change or authentication action was performed.

**Limit:** this proves public login/recovery navigation renders after deployment. It is
not protected production FBS, seller-workspace or warehouse-flow acceptance, and it does
not test email delivery, password reset, login credentials or signed-in authorization.
No production business data was created or changed.
