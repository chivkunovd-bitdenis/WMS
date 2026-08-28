import { Alert, Box, CircularProgress, GlobalStyles, Paper, Stack, Typography } from '@mui/material'
import { FfProductMarkingPrintProvider } from '../../components/FfProductMarkingPrintProvider'
import type { FfInboundRequestController } from './FfInboundRequestViewController'
import { FfInboundRequestHeader } from './FfInboundRequestHeader'
import { FfInboundRequestSortingPanel } from './FfInboundRequestSortingPanel'
import { FfInboundRequestLines } from './FfInboundRequestLines'
import { FfInboundRequestSortingWait } from './FfInboundRequestSortingWait'
import { FfInboundRequestDiscrepancies } from './FfInboundRequestDiscrepancies'
import { FfInboundRequestPackages } from './FfInboundRequestPackages'
import { FfInboundRequestDistribution } from './FfInboundRequestDistribution'
import { FfInboundRequestDialogs } from './FfInboundRequestDialogs'

export function FfInboundRequestViewBody({ controller }: { controller: FfInboundRequestController }) {
  const {
    busy,
    detail,
    error,
    token,
  } = controller

  if (busy && !detail) {
    return (
      <Stack sx={{ py: 6, alignItems: 'center' }} data-testid="ff-inbound-doc-loading">
        <CircularProgress />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Загрузка…
        </Typography>
      </Stack>
    )
  }

  return (
    <FfProductMarkingPrintProvider token={token}>
    <GlobalStyles
      styles={{
        'body > [aria-hidden="true"]': {
          width: '100vw',
          maxWidth: '100vw',
          overflowX: 'hidden',
        },
      }}
    />
    <Box
      data-testid="ff-inbound-doc-root"
      sx={{ width: '100%', minWidth: 0, maxWidth: '100%', boxSizing: 'border-box' }}
    >
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-inbound-doc-error">
          {error}
        </Alert>
      ) : null}
      {detail?.marketplace_warning ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="ff-inbound-marketplace-warning">
          {detail.marketplace_warning}
        </Alert>
      ) : null}

      {!detail ? (
        <Alert severity="warning">Заявка не найдена или недоступна.</Alert>
      ) : (
        <Paper
          variant="outlined"
          sx={{
            p: 2,
            minHeight: '38vh',
            width: '100%',
            minWidth: 0,
            maxWidth: '100%',
            boxSizing: 'border-box',
            overflowX: 'hidden',
          }}
        >
          <FfInboundRequestHeader controller={controller} />
          <FfInboundRequestSortingPanel controller={controller} />
          <FfInboundRequestLines controller={controller} />
          <FfInboundRequestSortingWait controller={controller} />
          <FfInboundRequestDiscrepancies controller={controller} />
          <FfInboundRequestPackages controller={controller} />
          <FfInboundRequestDistribution controller={controller} />
        </Paper>
      )}
      <FfInboundRequestDialogs controller={controller} />
    </Box>
    </FfProductMarkingPrintProvider>
  )
}
