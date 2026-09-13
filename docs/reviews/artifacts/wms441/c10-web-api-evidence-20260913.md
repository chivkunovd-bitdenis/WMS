# WMS-441 C10: web/API evidence, 2026-09-13

This is a bounded web/API check, recorded separately while the analyst updates
the shared requirements checklist. It is not an acceptance verdict and does not
cover the TSD part of C10 or historical recovery.

## Isolated runtime and data

- Web: `http://127.0.0.1:5204`, started with its API proxy directed to the
  current synthetic backend at `http://127.0.0.1:18084`.
- Tenant: local synthetic `wms-test`; no production tenant or shared final-review
  fixture was used.
- Document created for this check: `983b44bd-7b85-4950-976e-f1be434bc2e6`,
  displayed as `№000023`, waybill marker `WMS441-C10-WEB-FINAL-synthetic`.
- One unit of `WMS-441 mixed product 1789293654-9907` was accepted and entered
  sorting for this document.

## Observed web path

1. The modern sorting page opened the document by `open_inbound`; before action
   it showed status `В сортировке` and `1` unit remaining.
2. In the product row, the operator used `Положить в место`, chose
   `Ячейка W441-MIX-B`, kept quantity `1`, and pressed `Положить`.
3. The reread of that web card showed `Оприходовано`, `0` units remaining,
   `Всё расставлено по ячейкам`, and `W441-MIX-B — 1 шт`.
4. Closing the card returned to the modern web sorting queue. Its active rows
   contained documents `№000018`, `№000015`, `№000010`, `№000006`, `№000003`,
   and `№000017`; it did not contain `№000023`.

## Independent API reread

Immediately after the UI result, authenticated reads from the same current
synthetic backend returned:

```json
{
  "document": {
    "id": "983b44bd-7b85-4950-976e-f1be434bc2e6",
    "display_number": "№000023",
    "status": "done",
    "sorting_remaining_qty": 0
  },
  "active_sorting_queue_contains_document": false,
  "list_row": {
    "status": "done",
    "sorting_remaining_qty": 0
  }
}
```

The available web/API subset therefore proves the modern web completion,
server state `done`, zero remainder, and disappearance from the active web/API
sorting queue for this isolated document. TSD disappearance and reopen/recovery
were deliberately not run here because the emulator was reserved for the
parallel Astra check.
