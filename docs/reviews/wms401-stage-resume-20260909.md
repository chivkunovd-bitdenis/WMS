# WMS-401 — staging verification after reboot, 2026-09-09

The already uploaded deployment `a4ec12eb-3607-40e9-813f-36f9e2195d66` is **SUCCESS**. No new deployment was started during this verification. The runtime reports that exact deployment ID. Its 428 Python files under `/app/app` and `/app/alembic` match SHA256 hashes generated directly from `git archive aa7de3de8a965d1088ec44db1bb5f41a766d9dc5 backend/app backend/alembic`: zero missing files, zero extra files, zero mismatches.

The staging target remains project `c28e681d-4535-4c96-ac97-c7b600a7f8e4`, environment `58a08b66-1290-45a2-8737-e3d7408389e5`, WMS service `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`. Railway reports image digest `sha256:16758ad5ae91eddbc4340fc8407d95de467e536a4536e4022b44e4c3d638eb09`. The changed `app/services/fbs_picking_service.py` hash is `672f9bedca10e6fd1713e7d8f5638ebde462df1ea7d5f1148e2918a9c836adbf` in both Git and runtime.

At 11:12:42 UTC, public `https://wms-production-780c.up.railway.app/health` returned HTTP 200 and `{"status":"ok"}`. The health response was recorded using curl with normal TLS verification. A preceding Python urllib capture failed with a local certificate verification error (`unable to get local issuer certificate`); TLS verification was not disabled, and curl independently completed successfully.

The service is ready for the existing APK regression A → B → product. READY was sent to `mobile_resume` and root immediately after verification. This report does not claim APK acceptance: the author did not touch the AVD or write application data. No frontend, production deployment, settings, variables or credentials were changed.

Evidence: [verification and manifests](artifacts/wms401-stage-resume-20260909/verification.json), [runtime hashes](artifacts/wms401-stage-resume-20260909/runtime-python-sha256.json), [exact-source hashes](artifacts/wms401-stage-resume-20260909/source-python-sha256.json), [deployment metadata](artifacts/wms401-stage-resume-20260909/deployment.json), [health response](artifacts/wms401-stage-resume-20260909/health.txt).
