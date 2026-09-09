# WMS-396 — mobile check endpoint from actual API origins

At 12:28:52–12:28:55 UTC on 2026-09-09, both actual API origins returned **HTTP 451 with an empty body** for one synthetic request each to `https://mobile.api.crpt.ru/mobile/check`.

The production request ran inside `wms_prod-api-1` through the existing SSH connection to `root@sellerfocus.pro`. The staging request ran inside Railway WMS service `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`, project `c28e681d-4535-4c96-ac97-c7b600a7f8e4`, environment `58a08b66-1290-45a2-8737-e3d7408389e5`.

Each origin used its installed `httpx 0.28.1` and sent exactly one POST with JSON `{"code":"WMS396_SYNTHETIC_INVALID_CODE"}`. The request used normal TLS verification, the JSON content type, no token, no custom identity headers, no redirects and no retry. There was no alternate endpoint, proxy/VPN bypass or real marking code.

Both responses contained the allowlisted headers `server: nginx`, `content-length: 0` and the corresponding date. The production response date was `Wed, 09 Sep 2026 12:28:52 GMT`; staging was `Wed, 09 Sep 2026 12:28:55 GMT`. Both bodies were zero bytes, so there were no JSON fields to retain. The diagnostic retains only a header allowlist and scalar body-field allowlist; it does not retain cookies, credentials or arbitrary response content.

These are received HTTP responses, not DNS, connection or TLS exceptions. No HTTP 200 or code-verification result was returned. The empty body does not establish why the request was refused or which policy caused the refusal. The diagnostic does not infer that reason from the status number.

No application code, database data, deployment, credentials or AVD state was changed. The author coordinated the report index with opus_resume and waited for its commit before saving only this diagnostic's files. No additional Opus review was started.

Evidence: [production](artifacts/wms396-mobile-network-20260909/production.json), [staging](artifacts/wms396-mobile-network-20260909/staging.json), [exact single-request probe](artifacts/wms396-mobile-network-20260909/probe.py).
