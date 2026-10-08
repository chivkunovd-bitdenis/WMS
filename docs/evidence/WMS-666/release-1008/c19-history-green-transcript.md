# C19 and historical-entry focused verification

- Candidate base: `c8bb2d129e4b0bc4017d6b2ad05914d6d1d49511`.
- Workspace source SHA-1: `c4e8608e3e8c63e7e43fd5176b5e259201161cb9`.
- C19 test SHA-1: `ac236de5e496add14d1552f7f5a348f31e4ff777`.
- Historical-entry test SHA-1: `eb7fe71a00d11ad92d2b4773683cb589fcd1a097`.
- Command: `frontend/node_modules/.bin/vitest run src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx src/screens/v2/FfFbsSupplyWorkspace.wms666.history.dom.test.tsx --pool=threads --maxWorkers=1 --minWorkers=1` from `frontend/`.
- Result: 2 test files passed, 2 tests passed, 0 failed; duration 167.71s. C19 partial/reopen/page-refresh behavior passed, and historical `in_delivery` taskless entry passed without sticker preparation or `start-work`.
- Output provenance: compact result transcribed from the completed Vitest tool output in this task; this file is an execution summary, not a byte-for-byte stdout capture. The output reported MUI/DOM prop warnings, but both tests completed successfully.

The sparse checkout was missing the test's frozen `facts.json` fixture on the first collection attempt. The exact tracked fixture was restored into the sparse view before the successful run; no fixture contents or test expectations were changed.
