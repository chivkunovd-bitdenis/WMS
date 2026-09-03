import { useCallback, useEffect, useState } from 'react'
import { Box, Collapse, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'

import { apiUrl } from '../../api'
import { AppDialog, ErrorNotice, IconAction, SecondaryAction, StatusChip } from '../../ui-kit'

/**
 * История поставки FBS: что с ней и её заказами происходило, по часам.
 *
 * Отдельного экрана заказа в системе нет, поэтому историю ведём по поставке —
 * заказ живёт внутри неё. Однотипные записи склеены: печать сорока стикеров
 * даёт одну строку, а номера прячутся внутрь неё. Без этого история одной
 * поставки — это полсотни одинаковых строк, по которым ничего не найти.
 */

const MOSCOW_TIME_ZONE = 'Europe/Moscow'

export type FbsSupplyHistoryEvent = {
  at: string
  kind: string
  title: string
  actor: string | null
  details: string | null
  items: string[]
}

export type FbsSupplyHistory = {
  supply_id: string
  supply_number: string
  status: string
  order_count: number
  events: FbsSupplyHistoryEvent[]
}

const TONE_BY_KIND: Record<string, 'ok' | 'warn' | 'neutral' | 'stop'> = {
  created: 'neutral',
  order: 'neutral',
  cancelled: 'stop',
  pick: 'neutral',
  packed: 'ok',
  marking: 'neutral',
  print: 'neutral',
  box: 'neutral',
  status: 'ok',
}

const KIND_LABELS: Record<string, string> = {
  created: 'поставка',
  order: 'заказ',
  cancelled: 'отмена',
  pick: 'подбор',
  packed: 'упаковка',
  marking: 'коды',
  print: 'печать',
  box: 'короба',
  status: 'статус',
}

function formatMoment(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: MOSCOW_TIME_ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function HistoryRow({ event }: { event: FbsSupplyHistoryEvent }) {
  const [open, setOpen] = useState(false)
  const hasItems = event.items.length > 0
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ width: 110, flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}
      >
        {formatMoment(event.at)}
      </Typography>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {event.title}
          </Typography>
          <StatusChip
            label={KIND_LABELS[event.kind] ?? event.kind}
            tone={TONE_BY_KIND[event.kind] ?? 'neutral'}
          />
          {hasItems ? (
            <IconAction
              title={open ? 'Свернуть подробности' : 'Показать подробности'}
              onClick={() => setOpen((value) => !value)}
              testId={`fbs-supply-history-toggle-${event.at}-${event.kind}`}
            >
              <ExpandMoreIcon
                fontSize="small"
                sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: '.15s' }}
              />
            </IconAction>
          ) : null}
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
        {hasItems ? (
          <Collapse in={open} unmountOnExit>
            <Stack sx={{ pl: 1, mt: 0.5, borderLeft: 2, borderColor: 'divider' }}>
              {event.items.map((item, index) => (
                <Typography key={`${item}-${index}`} variant="caption" color="text.secondary">
                  {item}
                </Typography>
              ))}
            </Stack>
          </Collapse>
        ) : null}
      </Box>
    </Stack>
  )
}

export function FbsSupplyHistoryTimeline({ history }: { history: FbsSupplyHistory }) {
  if (!history.events.length) {
    return (
      <Typography color="text.secondary" data-testid="fbs-supply-history-empty">
        По этой поставке событий не записано.
      </Typography>
    )
  }
  return (
    <Stack spacing={1.5} data-testid="fbs-supply-history-timeline">
      {history.events.map((event, index) => (
        <HistoryRow key={`${event.at}-${event.kind}-${index}`} event={event} />
      ))}
    </Stack>
  )
}

export function FbsSupplyHistoryDialog({
  token,
  supplyId,
  open,
  onClose,
}: {
  token: string
  supplyId: string | null
  open: boolean
  onClose: () => void
}) {
  const [history, setHistory] = useState<FbsSupplyHistory | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!supplyId) return
    setLoading(true)
    setError(false)
    try {
      const response = await fetch(apiUrl(`/operations/fbs-supplies/${supplyId}/history`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('history')
      setHistory((await response.json()) as FbsSupplyHistory)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [supplyId, token])

  useEffect(() => {
    if (!open) return
    void load()
  }, [load, open])

  return (
    <AppDialog
      open={open}
      title={history ? `История поставки ${history.supply_number}` : 'История поставки'}
      onClose={onClose}
      maxWidth="md"
      testId="fbs-supply-history"
      actions={<SecondaryAction onClick={onClose}>Закрыть</SecondaryAction>}
    >
      {error ? (
        <ErrorNotice testId="fbs-supply-history-error">
          Не удалось загрузить историю поставки
        </ErrorNotice>
      ) : loading || !history ? (
        <Typography color="text.secondary">Загружаем…</Typography>
      ) : (
        <>
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            Заказов в поставке: {history.order_count}
          </Typography>
          <FbsSupplyHistoryTimeline history={history} />
        </>
      )}
    </AppDialog>
  )
}
