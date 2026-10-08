# WMS-666: WMS test-stage deployment receipt

Recorded 2026-10-08. This receipt separates the code SHA served by the test stage from the canonical merge SHA and from the pending operator browser acceptance.

## Deployment identity and health

The release candidate `ff0110ddbbd2b6b28df2720ad44a9d2c86cdecca` was merged into `etalon` through PR [#412](https://github.com/chivkunovd-bitdenis/WMS/pull/412) using a regular merge, producing canonical commit `61012808c26ba8dabcd271ef21bbbc362caaffaa` at 2026-10-08 11:09:52 UTC. The test stage currently serves the candidate SHA `ff0110d`; it has not been redeployed from the merge commit.

The target is Railway project `loyal-wonder` (`c28e681d-4535-4c96-ac97-c7b600a7f8e4`), environment `58a08b66-1290-45a2-8737-e3d7408389e5`. Railway labels that environment `production`, but this is the authorized test stack, not the WMS production VPS.

| Service | Service ID | Deployment ID | Source |
| --- | --- | --- | --- |
| WMS API | `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc` | `2c2d0ba4-f25a-4421-aae5-eb34e65ec663` | `ff0110ddbbd2b6b28df2720ad44a9d2c86cdecca` |
| Web | `f2ad51a8-009d-488c-9d64-7054072ccac6` | `e95b4369-9db4-499b-b772-5bfd27013caa` | `ff0110ddbbd2b6b28df2720ad44a9d2c86cdecca` |
| Worker | `ed8faf85-069f-4e94-8d6c-d76899165687` | `5b8c4bdf-ef89-4722-96b2-8ab497aae076` | `ff0110ddbbd2b6b28df2720ad44a9d2c86cdecca` |
| Beat | `d3355f36-aa1e-48c9-b69c-9e6005c4e1d9` | `3325e0f2-8687-4f1e-828c-2ace8dc7d04e` | `ff0110ddbbd2b6b28df2720ad44a9d2c86cdecca` |
| WB emulator | `582b4add-d338-424c-be03-9bb66af6c8f0` | `bd4e28f4-40cb-4a13-8270-e328c89c8479` | Separate emulator service; no WMS source SHA |

The four WMS services reported `SUCCESS/RUNNING`. The standard staging smoke returned HTTP 200 from the web root, the web `/api/health` proxy, and the backend `/health` endpoint. The non-secret `WILDBERRIES_MARKETPLACE_API_BASE` setting on WMS, worker, and beat points to `http://wb-emulator.railway.internal:8000`. The other WB API base settings have not been verified, so this receipt does not claim that every possible WB request is emulator-routed.

## CI on the canonical merge

The exact merge SHA `61012808c26ba8dabcd271ef21bbbc362caaffaa` passed CI run [37768257092](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37768257092), including all 13 jobs. The dedicated real-stack workflows also passed: [FBS main screen 37768257020](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37768257020), [FBS picking 37768257059](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37768257059), and [WB packing stickers 37768257026](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37768257026). The dependent trusted process-integrity workflow was still pending when this receipt was written: run `37769789356`.

The runtime portions of `backend/app`, `frontend/src`, and `tools/print-agent` are unchanged between the accepted native-print proof source `af5b5aa15210167ee1f943943871f6052150c791` and deployed source `ff0110ddbbd2b6b28df2720ad44a9d2c86cdecca`; the intervening differences in those trees are test files only. The accepted print proof therefore covers the same print runtime as the staged candidate, but it is a local emulated-handler proof rather than a stage UI run.

## Ordinary and grouped print input/output proof

The accepted proof used the actual Direct Print Handler with a local emulated sink. Its exact source file is `docs/evidence/WMS-666/release-1008/p2-prefix/native-final-af5/native-final-joins.json` (source SHA `af5b5aa…`, handler fingerprint `2a480705fd34f6f5690e7eae215fa2a4de466a6b4a0e1b08f75dcd9c110a99e1`). Each row records captured job/order/decoded content, rendered PNG SHA-256, handler receipt, and sink PNG SHA-256; all 12 rows had `join_valid=true`, with rendered, handler, and sink hashes equal. Case input JSON hashes were ordinary `96d94bf04b77a1257380bc3912b17f27f53a2361404ab30dbd59d39fae8fef5a` and grouped `867d01c0d010510e6d66ffd9db5a913324e0d9e4bc07e667a96e0fc37504bd12`.

| Path | Job key | Order | Captured content | Handler receipt | PNG SHA-256 |
| --- | --- | --- | --- | --- | --- |
| Ordinary | `5f8dcaa6-bada-4831-ba6d-42fa8402d830` | `a25420c2-b255-4d89-b52f-cb44da2e5fb7` | sticker `*WMS666-800392` | `emulator-0001-8ee34fda516b` | `8ee34fda516b0f669eb7fec14463234f805f623745f2e415302c035935d7ca67` |
| Ordinary | `…:chz` | same | KIZ `010460043993125321KIZTAPE0000000000` | `emulator-0002-f2f4c4632159` | `f2f4c4632159ca777baaedc16c7d402e33a9d228e05f94b82b87e83db3ac9261` |
| Ordinary | `…:chz:c2` | same | KIZ `010460043993125321KIZTAPE0000000000` | `emulator-0003-f2f4c4632159` | `f2f4c4632159ca777baaedc16c7d402e33a9d228e05f94b82b87e83db3ac9261` |
| Ordinary | `fc34f4dc-72a7-4c2b-bc54-c1f4a748ba4c` | `635d2f04-00dc-4c6d-a368-c0ae227b297e` | sticker `*WMS666-800393` | `emulator-0004-ffebd4debcd7` | `ffebd4debcd7e4fe6b94c65bdca3b442869921b819c1bfc66806c84e9c836d55` |
| Ordinary | `…:chz` | same | KIZ `010460043993125321KIZTAPE0000000001` | `emulator-0005-cb9e8ba5ed4a` | `cb9e8ba5ed4adefc15bd0f0df7b2864d64b59e2075beea00b9612ff7a880938a` |
| Ordinary | `…:chz:c2` | same | KIZ `010460043993125321KIZTAPE0000000001` | `emulator-0006-cb9e8ba5ed4a` | `cb9e8ba5ed4adefc15bd0f0df7b2864d64b59e2075beea00b9612ff7a880938a` |
| Grouped | `abcc841b-e75c-4438-ac6b-23a2c8a38ac0` | `e4ac808e-d8aa-402a-a140-275ae2b95cfa` | sticker `*WMS666-800392` | `emulator-0013-8ee34fda516b` | `8ee34fda516b0f669eb7fec14463234f805f623745f2e415302c035935d7ca67` |
| Grouped | `…:chz` | same | KIZ `010460043993125321KIZTAPE0000000000` | `emulator-0014-f2f4c4632159` | `f2f4c4632159ca777baaedc16c7d402e33a9d228e05f94b82b87e83db3ac9261` |
| Grouped | `…:chz:c2` | same | KIZ `010460043993125321KIZTAPE0000000000` | `emulator-0015-f2f4c4632159` | `f2f4c4632159ca777baaedc16c7d402e33a9d228e05f94b82b87e83db3ac9261` |
| Grouped | `a8f9ce9a-cabd-496f-88cd-42e753eac6b4` | `26ee918e-0a39-4507-9cf4-ea2620d7c494` | sticker `*WMS666-800393` | `emulator-0016-ffebd4debcd7` | `ffebd4debcd7e4fe6b94c65bdca3b442869921b819c1bfc66806c84e9c836d55` |
| Grouped | `…:chz` | same | KIZ `010460043993125321KIZTAPE0000000003` | `emulator-0017-d5b0dd700c56` | `d5b0dd700c564239fe04d8774cf76fbb1e0e6c56112367b99c7422c82670637b` |
| Grouped | `…:chz:c2` | same | KIZ `010460043993125321KIZTAPE0000000003` | `emulator-0018-d5b0dd700c56` | `d5b0dd700c564239fe04d8774cf76fbb1e0e6c56112367b99c7422c82670637b` |

This proves rendering and delivery to the emulated native sink only. Physical printer output and paper were not tested.

## Operator acceptance still pending

No authenticated stage browser session was available when deployment and CI were verified. The existing Chrome tab was at the login screen; no password reset, credential change, token creation, or stage data mutation was performed. Therefore current-SHA live operator checks for ordinary/group packing, selected/all packing, refreshed sticker and KIZ behavior, manual/continuous printing, recovery, and picking-list rendering remain pending a user login. The existing C11 stage evidence is from an earlier release and is not presented as acceptance of this SHA.

No production deployment or production merge was performed.
