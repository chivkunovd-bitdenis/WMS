import { Alert } from '@mui/material'
import type { FfInboundRequestController } from './FfInboundRequestViewController'

export function FfInboundRequestSortingWait({ controller }: { controller: FfInboundRequestController }) {
  const {
    sortingView,
    receptionClosed,
  } = controller

  return (
    <>
          {sortingView && !receptionClosed ? (
            <Alert severity="info" sx={{ mt: 2 }} data-testid="ff-inbound-sorting-wait-reception">
              Сначала завершите приёмку в разделе <strong>Приёмка</strong>.
            </Alert>
          ) : null}

    </>
  )
}
