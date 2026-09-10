# WMS-270/377: actual Caddy client-IP header regression, 2026-09-10

The one-line change in `deploy/Caddyfile.http` replaces
`header_up X-Forwarded-For {http.request.client_ip}` with
`header_up X-Forwarded-For {client_ip}`. No AUTH application code changed.
Parent commit: `1922a2242ad626a9618cb2b7300e6cf500d25b4d`.
Tested fixed Caddyfile Git blob: `b3b2a430702ec03d6f3c7ce63e80d54ba49d43e0`.

## Independently executed evidence

The local Docker client was available, but its daemon socket was absent. Instead,
the test used the official macOS arm64 Caddy **v2.11.4** executable, downloaded
from the [official release](https://github.com/caddyserver/caddy/releases/tag/v2.11.4).
The archive matched the release's SHA-512 checksum. Its SHA-256 was
`9efb0af2d6cf09cfb5053c0e51721b9b3d4956d346234f39368d943d25a3c9a7`.
Binary version output: `v2.11.4 h1:XKxkMTgNSizEvKG6QHue6cAsFOteU2qA61w2tKkCWi0=`.

`scripts/deploy/tests/test_caddy_client_ip.py` launches actual Caddy and a Python
HTTP upstream on temporary **127.0.0.1** ports. It reads the actual repository
Caddyfile, retaining its routes, strict proxy parsing and header expression.
It substitutes the listener/upstream addresses, disables Caddy administration,
automatic HTTPS and config persistence, and adds `127.0.0.1/32` to trusted proxies
only for the simulated trusted-edge cases. The untrusted cases retain the actual
production trust list. No host network, production service, database or login
endpoint is used. Requests contain only synthetic documentation-range IPs.

The upstream echoes the header actually received after `reverse_proxy`; this is
not a Caddy adaptation or configuration-text assertion. Exact header-list equality
also detects duplicate headers, unresolved placeholders and untrimmed chains.

| Request | Upstream X-Forwarded-For with fix |
| --- | --- |
| Trusted peer, client `203.0.113.10` | `203.0.113.10` |
| Trusted peer, distinct client `203.0.113.11` | `203.0.113.11` |
| Trusted peer, `203.0.113.10, 172.18.0.4` | `203.0.113.10` |
| Trusted peer, spoof prefix `198.51.100.99, 203.0.113.10, 172.18.0.4` | `203.0.113.10` |
| Trusted peer, missing XFF | `127.0.0.1` |
| Untrusted peer, missing XFF | `127.0.0.1` |
| Untrusted peer, spoof `198.51.100.99` | `127.0.0.1` |
| Untrusted peer, spoof chain `198.51.100.99, 172.18.0.4` | `127.0.0.1` |

Fixed config: **2 test methods / 8 request cases passed** in 1.200 seconds.
Caddy PIDs **34589**, **34595** were terminated and reaped by the harness.

Negative control: the same test and binary were run against the unmodified
Caddyfile extracted with `git show HEAD:deploy/Caddyfile.http` while HEAD was the
parent SHA above. **All 8 cases failed**, and the actual upstream header in each
was the literal `{http.request.client_ip}`. Test exit code was 1, as required by
the negative-control wrapper. Caddy PIDs **34638**, **34639** were terminated and
reaped. This reproduces the defect and demonstrates that reverting the line is
caught by a real request regression.

Focused Ruff check on the new test and `git diff --check` passed. No full suite
was run. The existing unrelated `auth270-security-scoped-20260910.log` was neither
read nor included in this change.

## Reproduction and limits

```sh
python3 -B scripts/deploy/tests/test_caddy_client_ip.py --caddy /absolute/path/to/caddy
```

Use `--caddyfile /path/to/baseline/Caddyfile` to run the same assertions against
the old configuration; the expected result is failure. The executable is required
explicitly: missing Caddy cannot produce a passing skip. Temporary config/data
directories and all child processes are cleaned up by the harness.

This proves the one-line fix with actual Caddy v2.11.4 on an isolated local
request-to-upstream path. The exact production Caddy version was not established
in this pass. It does not claim verification of the deployed outer-Caddy chain,
Uvicorn client-IP handling, limiter state, external ports or browser behavior.
Production rollback/deployment and independent release review remain with the
coordinator. No production actions were performed. WMS-111/112 remain STOP.
