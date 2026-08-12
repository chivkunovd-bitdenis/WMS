import { useEffect, useRef } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { Screen } from '../AppV2Screens'
import { formatDateTimeLocal } from '../../utils/formatDateTimeLocal'
import { movementTypeLabel } from '../../utils/movementTypeLabel'

type GlobalMovementRow = {
  id: string
  sku_code: string
  created_at?: string
  quantity_delta: number
  movement_type: string
}

type Props = {
  globalMovements: GlobalMovementRow[]
  onRefreshGlobalMovementsClick: () => void
  isFulfillmentAdmin: boolean
  opsBusy: boolean
  backgroundJobStatus: string | null
  backgroundJobResult: string | null
  onStartMovementsDigestJob: () => void
}

export function MovementsScreen({
  globalMovements,
  onRefreshGlobalMovementsClick,
  isFulfillmentAdmin,
  opsBusy,
  backgroundJobStatus,
  backgroundJobResult,
  onStartMovementsDigestJob,
}: Props) {
  const autoLoadStarted = useRef(false)

  useEffect(() => {
    if (autoLoadStarted.current) return
    autoLoadStarted.current = true
    void onRefreshGlobalMovementsClick()
  }, [onRefreshGlobalMovementsClick])

  return (
    <Screen title="Журнал движений" subtitle="Последние операции по складу">
      {isFulfillmentAdmin ? (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid="background-job-section">
          <Stack
            spacing={1.5}
            direction={{ xs: 'column', sm: 'row' }}
            sx={{ alignItems: { sm: 'center' } }}
          >
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
              Сводка помогает руководителю быстро проверить последние изменения остатков.
            </Typography>
            <Button
              variant="outlined"
              type="button"
              data-testid="background-job-start"
              disabled={opsBusy}
              onClick={onStartMovementsDigestJob}
            >
              {opsBusy ? 'Считаем...' : 'Сводка по движениям'}
            </Button>
            <Chip
              size="small"
              variant="outlined"
              label={backgroundJobStatus ? `Статус: ${backgroundJobStatus}` : 'Сводка не запускалась'}
              data-testid="background-job-status"
            />
          </Stack>
          {backgroundJobResult ? (
            <Alert severity="info" sx={{ mt: 1.5 }} data-testid="background-job-result">
              {backgroundJobResult}
            </Alert>
          ) : null}
        </Paper>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2 }} data-testid="global-movements-section">
        <Stack spacing={1.5}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle1">Последние движения</Typography>
              <Typography variant="body2" color="text.secondary">
                Приёмка, перемещения и отгрузки загружаются сразу при открытии журнала.
              </Typography>
            </Box>
            <Button
              variant="outlined"
              type="button"
              data-testid="global-movements-refresh"
              onClick={onRefreshGlobalMovementsClick}
            >
              Обновить
            </Button>
          </Stack>
          <TableContainer data-testid="global-movements-list">
            <Table size="small" data-testid="global-movements-table">
              <TableHead>
                <TableRow>
                  <TableCell>Время</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell align="right">Изменение</TableCell>
                  <TableCell>Операция</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {globalMovements.map((m) => (
                  <TableRow key={m.id} data-testid="global-movement-row">
                    <TableCell>{m.created_at ? formatDateTimeLocal(m.created_at) : '—'}</TableCell>
                    <TableCell>{m.sku_code}</TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        fontWeight: 700,
                        color: m.quantity_delta < 0 ? 'error.main' : 'success.main',
                      }}
                    >
                      {m.quantity_delta > 0 ? '+' : ''}
                      {m.quantity_delta}
                    </TableCell>
                    <TableCell>{movementTypeLabel(m.movement_type)}</TableCell>
                  </TableRow>
                ))}
                {globalMovements.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" color="text.secondary">
                        Движений пока нет. После приёмки, перемещения или отгрузки строки появятся здесь автоматически.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </Paper>
    </Screen>
  )
}
