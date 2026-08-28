import { Alert, Box, Button, Chip, CircularProgress, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import type { FfInboundRequestController } from './FfInboundRequestViewController'
import { discrepancyActStatusRu, discrepancyActTitle, signedQty } from './FfInboundRequestViewTypes'

export function FfInboundRequestDiscrepancies({ controller }: { controller: FfInboundRequestController }) {
  const {
    isFulfillmentAdmin,
    linkedDiscrepancyActs,
    discrepancyActsBusy,
    discrepancyActsError,
    sortingView,
    resolveDiscrepancyAct,
  } = controller

  return (
    <>
          {isFulfillmentAdmin &&
          !sortingView &&
          (linkedDiscrepancyActs.length > 0 || discrepancyActsError) ? (
            <Paper
              variant="outlined"
              sx={{ mt: 2, p: 1.5 }}
              data-testid="ff-inbound-discrepancy-acts"
            >
              <Stack spacing={1.25}>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Акты расхождения
                  </Typography>
                  {discrepancyActsBusy ? (
                    <CircularProgress size={18} data-testid="ff-inbound-discrepancy-acts-loading" />
                  ) : null}
                </Stack>
                {discrepancyActsError ? (
                  <Alert severity="error" data-testid="ff-inbound-discrepancy-acts-error">
                    {discrepancyActsError}
                  </Alert>
                ) : null}
                {linkedDiscrepancyActs.map((act) => (
                  <Box
                    key={act.id}
                    sx={{ borderTop: 1, borderColor: 'divider', pt: 1 }}
                    data-testid="ff-inbound-discrepancy-act"
                  >
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1}
                      sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', mb: 1 }}
                    >
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {discrepancyActTitle(act.created_at)}
                        </Typography>
                        <Chip
                          size="small"
                          label={discrepancyActStatusRu(act.status)}
                          color={
                            act.status === 'approved'
                              ? 'success'
                              : act.status === 'rejected'
                                ? 'error'
                                : 'default'
                          }
                          data-testid="ff-inbound-discrepancy-act-status"
                        />
                      </Stack>
                      {act.status === 'confirmed' ? (
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            variant="contained"
                            disabled={discrepancyActsBusy}
                            onClick={() => void resolveDiscrepancyAct(act.id, 'approve')}
                            data-testid="ff-inbound-discrepancy-act-approve"
                          >
                            Утвердить
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            disabled={discrepancyActsBusy}
                            onClick={() => void resolveDiscrepancyAct(act.id, 'reject')}
                            data-testid="ff-inbound-discrepancy-act-reject"
                          >
                            Отклонить
                          </Button>
                        </Stack>
                      ) : null}
                    </Stack>
                    <Table size="small" data-testid="ff-inbound-discrepancy-act-lines">
                      <TableHead>
                        <TableRow>
                          <TableCell>Товар</TableCell>
                          <TableCell align="right">Расхождение</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {act.lines.map((line) => (
                          <TableRow key={line.id} data-testid="ff-inbound-discrepancy-act-line">
                            <TableCell>
                              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                {line.sku_code}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {line.product_name}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">{signedQty(line.quantity)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                ))}
              </Stack>
            </Paper>
          ) : null}

    </>
  )
}
