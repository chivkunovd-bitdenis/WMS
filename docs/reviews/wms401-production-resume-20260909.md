# WMS-401 — independent production artifact verification

Read-only verification at 11:38 UTC on 2026-09-09: **PASS**. Production `/opt/wms` HEAD is exactly `c3aa4dfaccbc99c6d58cf9e5a864bc248cc8ae3f`. The author began runtime inspection only after root reported that the ordinary production deployment had completed successfully. No deployment was started or repeated by this verification.

All 428 runtime Python files under `/app/app` and `/app/alembic` match SHA256 hashes generated directly from Git archive source `aa7de3de8a965d1088ec44db1bb5f41a766d9dc5`. Git confirms no changes to these directories between that source and the deployed merge. There are zero missing, additional or mismatching Python files.

All 179 files in the active web container `/srv` match the prior production manifest at `a75ed98a03e0500e41a69e5b617a27587bed9792`, which had already been matched to the WMS-409 staging artifact. There are zero missing, additional or mismatching frontend files. A fresh Git comparison also confirms no frontend source changes between that previous production SHA and the deployed merge.

Public `https://wms.sellerfocus.pro/api/health` returned HTTP 200 and `{"status":"ok"}`. The public `/`, `assets/ff-DFfJOXYQ.js` and `assets/FfInboundQueuePage-CmHWjBe5.js` responses returned HTTP 200 and their SHA256 hashes matched the active `/srv` files. Curl used normal TLS verification.

The API and web containers are running and are not restarting. Their image IDs were read directly:

- API: `sha256:4868fca05d5ebc9f258b538a8dd3316dfd7a900aaec12e309e03379b754f7268`.
- Web: `sha256:0844fa0b662735b4ab21b6e96f623fdbfca9bdec62bb82204e5ce7798c32580a`.

This check read Git, container files, limited container state and public HTTP responses. It did not write application data, operate other users' documents, change secrets, operate the AVD or run another deployment. It verifies source delivery and health; the APK scenario remains covered by the separate mobile evidence. Canonical backlog updates remain with root.

Evidence: [comparison and public checks](artifacts/wms401-production-resume-20260909/verification.json), [fresh runtime manifests](artifacts/wms401-production-resume-20260909/runtime.json), [expected Git and prior-frontend manifests](artifacts/wms401-production-resume-20260909/expected-manifests.json).
