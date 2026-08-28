import { Alert } from '@mui/material'
import { FfInboundSortingPanel } from './FfInboundSortingPanel'
import { isDoneStatus } from './inboundReceivingHelpers'
import type { FfInboundRequestController } from './FfInboundRequestViewController'

export function FfInboundRequestSortingPanel({ controller }: { controller: FfInboundRequestController }) {
  if (!controller.detail) return null

  const {
    token,
    requestId,
    onDirtyChange,
    detail,
    sortingView,
    receptionClosed,
    sortingRemainingTotal,
    loadDetail,
  } = controller

  return (
    <>
          {sortingView && receptionClosed ? (
            <>
              {isDoneStatus(detail.status) ? (
                <Alert severity="success" sx={{ mb: 2 }} data-testid="ff-sorting-posted-done">
                  Оприходовано — весь товар разложен по ячейкам хранения.
                </Alert>
              ) : null}
              <FfInboundSortingPanel
                token={token}
                requestId={requestId}
                warehouseId={detail.warehouse_id}
                completed={isDoneStatus(detail.status)}
                lines={(detail.lines ?? []).map((ln) => ({
                  product_id: ln.product_id,
                  sku_code: ln.sku_code,
                  product_name: ln.product_name,
                  actual_qty: ln.actual_qty,
                  posted_qty: ln.posted_qty ?? 0,
                }))}
                boxes={(detail.boxes ?? []).map((b) => ({
                  ...b,
                  remaining_qty: b.remaining_qty ?? 0,
                  lines: (b.lines ?? []).map((ln) => ({
                    ...ln,
                    posted_qty: ln.posted_qty ?? 0,
                    remaining_qty:
                      ln.remaining_qty ?? Math.max(0, ln.quantity - (ln.posted_qty ?? 0)),
                  })),
                }))}
                sortingRemainingQty={sortingRemainingTotal}
                onReload={async () => {
                  await loadDetail()
                }}
                onDirtyChange={onDirtyChange}
              />
            </>
          ) : null}

    </>
  )
}
