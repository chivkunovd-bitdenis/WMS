# WMS-396 — staging source and runtime verification

At 12:39:14 UTC on 2026-09-09, Railway deployment `de3f683a-adde-4580-ae0d-341356178d7a` was independently confirmed **SUCCESS**. The active container reports that exact `RAILWAY_DEPLOYMENT_ID`.

All 429 Python files under `/app/app` and `/app/alembic` match SHA256 hashes generated directly from `git archive 4f124cfa646431aa6ae4a1d949bcfdb8155eab1b backend/app backend/alembic`. There are zero missing files, zero additional files and zero mismatches. The new `app/services/public_marking_check.py` matches SHA256 `59c4a8606ded5b889e81989618a9b822a89c8ada1519629374dfda6510ca5660`.

The target is the existing staging project `c28e681d-4535-4c96-ac97-c7b600a7f8e4`, environment `58a08b66-1290-45a2-8737-e3d7408389e5`, WMS service `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`. Deployment metadata and the active Python files were read using the existing Railway CLI. The working SSH invocation passes the entire remote command as one argument after `--`: `"python -c " + shlex.quote(code)`.

This verification did not contact the marking endpoint, trigger a receiving check, modify application data or run another deployment. It proves delivery of the reviewed source to staging. The actual browser recheck is being performed separately by root, and no browser verdict is inferred from runtime hashes.

Evidence: [comparison](artifacts/wms396-stage-runtime-20260909/verification.json), [deployment metadata](artifacts/wms396-stage-runtime-20260909/deployment.json), [runtime hashes](artifacts/wms396-stage-runtime-20260909/runtime-python-sha256.json), [source hashes](artifacts/wms396-stage-runtime-20260909/source-python-sha256.json).

## Saved receiving recheck result

At 12:43:05 UTC, after root's actual browser recheck, a separate database read verified receiving request `05cd913b-7f50-4f64-9c45-d1b124737166` in tenant `9c31f3f4-ce62-4c1f-891a-295b278f1e69`. The request is still `sorting`. Its two product lines total four expected and four accepted units, zero posted units and zero defective units.

Both attached check snapshots contain `provider=mobile_check`, `http_status=451`, `status=unavailable` and the reason “Честный знак недоступен. Повторите проверку позже.” This confirms the stored result of the new transport; it does not claim successful external code verification. Two check snapshots and four accepted units are separate quantities.

The database transaction was explicitly READ ONLY. No new marking POST, scheduling operation, receipt mutation or raw code output occurred. Only allowlisted result fields and quantities were retained in [the sanitized receiving snapshot](artifacts/wms396-stage-runtime-20260909/receiving-recheck-sanitized.json).
