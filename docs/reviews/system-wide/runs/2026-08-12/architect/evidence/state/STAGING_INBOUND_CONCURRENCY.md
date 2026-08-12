# Sanitized inbound concurrency read-back

Captured 2026-08-12 on staging commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`. Both reproductions used distinct documents and products in isolated synthetic tenant `bc3d8e72-a011-4264-8dcf-77697579ebd0`.

| Run | Request / line | Parallel completion server timestamps, UTC | HTTP statuses | Document read-back | Balance read-back | Movement read-back |
|---|---|---|---|---|---:|---|
| 1 | `23e02d53-3676-40d3-aa9a-8e24f1298acb` / `b12641f0-186f-4059-908e-169b15ea1451` | `2026-08-12T10:22:43.888190165Z`; `2026-08-12T10:22:43.888196096Z` | `200`, `200` | `status=sorting`, expected `1`, actual `1` | `quantity=2` | 2 movements, delta sum `+2` |
| 2 | `18f5bd77-0a0b-41fa-b0de-bd0d9fc4b9d9` / `dc0ac104-642b-4939-8fdb-d73a831b9381` | `2026-08-12T10:22:46.869782266Z`; `2026-08-12T10:22:46.869788412Z` | `200`, `200` | `status=sorting`, expected `1`, actual `1` | `quantity=2` | 2 movements, delta sum `+2` |

The two lines agree independently: one accepted unit became two on-hand units while the document continued to display one actual unit. Credentials and authorization values were not retained.

The anomaly is intentionally retained as review evidence. No supported tenant-delete or safe global correction operation was found, and direct database deletion was outside the review scope.
