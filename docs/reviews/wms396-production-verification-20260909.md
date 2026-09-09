# WMS-396 — production verification prepared before deployment

A fresh read-only baseline was captured at 2026-09-09T12:54:16.077044+00:00. Production `/opt/wms` is still `c3aa4dfaccbc99c6d58cf9e5a864bc248cc8ae3f`. The current web `/srv` contains 179 files; their complete SHA256 manifest is saved. API, worker, beat and web are all running without restarting, and only their image IDs and limited state were retained.

The expected Python manifest contains 429 files from reviewed source `4f124cfa646431aa6ae4a1d949bcfdb8155eab1b`. A fresh Git diff verifies that subsequent source `0860fe221180f9d369c9ccbbe6697a6b33c153a4` changes only a test file and the canonical backlog; the production Python expectation is unchanged.

The prepared read-only script has two explicit modes. Only `--baseline` was executed for this checkpoint. Post-deployment mode requires `--expected-production-sha <merged SHA>` and must wait for root's READY. It will compare all 429 runtime Python files separately in API, celery_worker and celery_beat, compare all web files against this saved baseline, check limited container state, and read public health and index responses. It does not run deployments, modify data, call the marking endpoint or access credentials.

Evidence: [baseline](artifacts/wms396-production-verification-20260909/baseline.json), [expected Python files](artifacts/wms396-production-verification-20260909/expected-python.json), [prepared verification script](artifacts/wms396-production-verification-20260909/verify-production.py). No post-deployment verdict is claimed by this preparation checkpoint.
