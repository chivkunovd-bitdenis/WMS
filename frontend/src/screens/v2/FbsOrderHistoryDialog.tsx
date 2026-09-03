import { useCallback, useEffect, useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'

import { apiUrl } from '../../api'
import { AppDialog, ErrorNotice, SecondaryAction, StatusChip } from '../../ui-kit'

/**
 * История заказа FBS: что с ним происходило, по часам.
 *
 * Когда заказ повёл себя странно, восстановить картину было нечем — данные лежат
 * в разных таблицах, и человек собирал историю глазами по базе. Здесь она
 * приходит одним списком: подбор, упаковка, коды маркировки, печать документов и
 * события поставки, в которой заказ уехал.
 *
 * Окно самодостаточно: его можно открыть из любого места, где есть id заказа.
 */

const MOSCOW_TIME_ZONE = 'Europe/Moscow'

export type FbsHistoryEvent = {
  at: string
  kind: string
  title: string
  actor: string | null
  details: string | null
}

export type FbsOrderHistory = {
  order_id: string
  wb_order_id: number
  status: string
  wb_status: string | null
  supply_id: string | null
  events: FbsHistoryEvent[]
}

const TONE_BY_KIND: Record<string, 'ok' | 'warn' | 'neutral' | 'stop'> = {
  created: 'neutral',
  pick: 'neutral',
  packed: 'ok',
  packed_undone: 'warn',
  marking: 'neutral',
  print_requested: 'neutral',
  print_ready: 'ok',
  print_applied: 'ok',
  supply: 'neutral',
  status: 'ok',
}

function formatMoment(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: MOSCOW_TIME_ZONE,
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(new Date(value))
}

export function FbsOrderHistoryTimeline({ history }: { history: FbsOrderHistory }) {
  if (!history.events.length) {
    return (
      <Typography color="text.secondary" data-testid="fbs-history-empty">
        По этому заказу событий не записано.
      </Typography>
    )
  }
  return (
    <Stack spacing={1.5} data-testid="fbs-history-timeline">
      {history.events.map((event, index) => (
        <Stack
          key={`${event.at}-${index}`}
          direction="row"
          spacing={1.5}
          sx={{ alignItems: 'flex-start' }}
        >
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ width: 150, flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}
          >
            {formatMoment(event.at)}
          </Typography>
          <Box sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {event.title}
              </Typography>
              <StatusChip label={event.kind} tone={TONE_BY_KIND[event.kind] ?? 'neutral'} />
            </Stack>
            {event.details ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {event.details}
              </Typography>
            ) : null}
            {event.actor ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {event.actor}
              </Typography>
            ) : null}
          </Box>
        </Stack>
      ))}
    </Stack>
  )
}

export function FbsOrderHistoryDialog({
  token,
  orderId,
  open,
  onClose,
}: {
  token: string
  orderId: string | null
  open: boolean
  onClose: () => void
}) {
  const [history, setHistory] = useState<FbsOrderHistory | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!orderId) return
    setLoading(true)
    setError(false)
    try {
      const response = await fetch(apiUrl(`/operations/fbs-orders/${orderId}/history`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('history')
      setHistory((await response.json()) as FbsOrderHistory)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [orderId, token])

  useEffect(() => {
    if (!open) return
    void load()
  }, [load, open])

  return (
    <AppDialog
      open={open}
      title={history ? `История заказа ${history.wb_order_id}` : 'История заказа'}
      onClose={onClose}
      maxWidth="md"
      testId="fbs-order-history"
      actions={<SecondaryAction onClick={onClose}>Закрыть</SecondaryAction>}
    >
      {error ? (
        <ErrorNotice testId="fbs-history-error">Не удалось загрузить историю заказа</ErrorNotice>
      ) : loading || !history ? (
        <Typography color="text.secondary">Загружаем…</Typography>
      ) : (
        <FbsOrderHistoryTimeline history={history} />
      )}
    </AppDialog>
  )
}
