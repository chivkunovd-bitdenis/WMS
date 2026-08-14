# Stage Deploy Verification — WMS strict product gate

Дата: 2026-08-14, Europe/Moscow.

Verdict: `STAGE_DEPLOY_VERIFIED`.

## Что проверено

Stage развернут из итогового application commit после strict product/browser
gates. Этот artifact может быть сохранён отдельным docs-only commit после
деплоя; проверяемый код/сборка stage ниже привязаны именно к application deploy
SHA.

- application deploy SHA: `595bf93404794ade562b7f9fc4d6c1bdc09267c6`;
- `origin/staging` указывает на этот SHA;
- Railway backend service `WMS` deployment:
  `321617c0-5727-445d-a426-c6b2ee952b3c`, status `SUCCESS`;
- Railway frontend service `web` deployment:
  `063166b4-a27e-4071-a558-b0aeeaeecd24`, status `SUCCESS`;
- public web URL: `https://web-production-9e7c1.up.railway.app/`;
- public API URL: `https://wms-production-780c.up.railway.app/`.

## Smoke

`scripts/railway-staging-smoke.sh` passed:

- `GET /` -> HTTP 200;
- `GET /api/health` -> HTTP 200;
- SPA shell contains React root.

Direct checks:

- web proxy `/api/health` -> `{"status":"ok"}`;
- backend `/health` -> `{"status":"ok"}`;
- backend `/openapi.json` -> HTTP 200;
- web proxy `/api/openapi.json` -> HTTP 200.

## Browser Evidence

Live Chromium check was run against the public staging web URL, without using
or printing staging credentials.

- browser: Chromium;
- mode: `headless=false`;
- viewport: `1440x900`;
- screenshot:
  `stage-login-shell-1440x900.png`;
- JSON evidence:
  `stage-browser-smoke.json`;
- visible shell:
  - title `WMS · Фулфилмент`;
  - React root present;
  - Email field visible;
  - password field visible;
  - login button visible;
  - `/api/health` status 200.

## Build Proof

The deployed frontend HTML references:

`/assets/ff-BEgAjw6d.js`

The same asset is produced locally from the current tree when built with the
Railway Docker build args:

```bash
VITE_SELLER_PORTAL_URL=/seller/ VITE_FF_PORTAL_URL=/ npm run build
```

The HTTP `Last-Modified` header for the staging root after deploy was
`Fri, 14 Aug 2026 05:24:55 GMT`, replacing the stale 2026-08-12 build.

## Boundaries

This stage verification does not use or disclose credentials, does not open
secret panels, does not rotate secrets, and does not perform login-only or
irreversible marketplace actions. It verifies that the staged services are
deployed and reachable from the strict gate commit, and that the public UI shell
loads the expected build artifact.
