import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type FfInboundSummary = {
  id: string
  document_number?: string | null
  status: string
  line_count: number
  planned_delivery_date: string | null
  seller_name?: string | null
  created_at?: string
}

export type FfOutboundSummary = {
  id: string
  status: string
  line_count: number
  planned_shipment_date?: string | null
  created_at?: string
  warehouse_name?: string
  goods_qty_total?: number
  marketplace_label?: string
  seller_name?: string | null
}

type Me = {
  email: string
  organization_name: string
  role: string
  seller_name?: string | null
}

type FbsCalendarRow = {
  id: string
  date: string
  direction: string
  boxes_count: number
  shipment_type: 'FBS'
  title: string
}

type ShipmentCalendarRow = {
  id: string
  date: string
  direction: string
  boxesCount: number
  shipmentType: 'FBS' | 'FBO' | 'MP'
  title: string
  source: 'fbs' | 'fbo' | 'mp'
}

type Props = {
  me: Me
  token: string
  authHeaders: (token: string) => Record<string, string>
  isFulfillmentAdmin: boolean
  inboundSummaries: FfInboundSummary[]
  outboundSummaries: FfOutboundSummary[]
  onOpenInbound: (id: string) => void
  onOpenOutbound: (id: string) => void
  onOpenMarketplaceUnload: (id: string) => void
  onOpenFbsSupply: (id: string) => void
  mpUnloadSummaries?: FfOutboundSummary[]
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

function fmtKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function monthLabel(d: Date): string {
  return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
}

function monthGrid(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const firstDay = first.getDay()
  const startOffset = firstDay === 0 ? -6 : 1 - firstDay
  const start = addDays(first, startOffset)
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
  const lastDay = last.getDay()
  const endOffset = lastDay === 0 ? 0 : 7 - lastDay
  const end = addDays(last, endOffset)
  const days: Date[] = []
  for (let d = start; d <= end; d = addDays(d, 1)) {
    days.push(d)
  }
  return days
}

const dayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

export function FfDashboard({
  token,
  authHeaders,
  inboundSummaries: _inboundSummaries,
  outboundSummaries,
  mpUnloadSummaries = [],
  onOpenOutbound,
  onOpenMarketplaceUnload,
  onOpenFbsSupply,
}: Props) {
  const [monthOffset, setMonthOffset] = useState(0)
  const [fbsRows, setFbsRows] = useState<FbsCalendarRow[]>([])
  const [fbsBusy, setFbsBusy] = useState(false)
  const [fbsError, setFbsError] = useState<string | null>(null)

  const visibleMonth = useMemo(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth() + monthOffset, 1)
  }, [monthOffset])
  const days = useMemo(() => monthGrid(visibleMonth), [visibleMonth])
  const rangeStart = fmtKey(days[0]!)
  const rangeEnd = fmtKey(days[days.length - 1]!)

  useEffect(() => {
    let cancelled = false
    setFbsBusy(true)
    setFbsError(null)
    void fetch(apiUrl(`/operations/fbs-supplies/calendar?start_date=${rangeStart}&end_date=${rangeEnd}`), {
      headers: authHeaders(token),
    })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        return (await res.json()) as FbsCalendarRow[]
      })
      .then((rows) => {
        if (!cancelled) setFbsRows(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setFbsRows([])
          setFbsError(err instanceof Error ? err.message : 'Не удалось загрузить календарь FBS.')
        }
      })
      .finally(() => {
        if (!cancelled) setFbsBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [authHeaders, rangeEnd, rangeStart, token])

  const shipmentRows = useMemo<ShipmentCalendarRow[]>(() => {
    const fbs = fbsRows.map((row) => ({
      id: row.id,
      date: row.date,
      direction: row.direction,
      boxesCount: row.boxes_count,
      shipmentType: 'FBS' as const,
      title: row.title,
      source: 'fbs' as const,
    }))
    const mp = mpUnloadSummaries
      .filter((row) => row.status === 'submitted' && row.planned_shipment_date)
      .map((row) => ({
        id: row.id,
        date: row.planned_shipment_date!,
        direction: row.warehouse_name ?? 'Направление не указано',
        boxesCount: row.goods_qty_total ?? row.line_count,
        shipmentType: 'MP' as const,
        title: row.marketplace_label ?? 'Маркетплейс',
        source: 'mp' as const,
      }))
    const fbo = outboundSummaries
      .filter((row) => row.status === 'submitted' && row.planned_shipment_date)
      .map((row) => ({
        id: row.id,
        date: row.planned_shipment_date!,
        direction: row.warehouse_name ?? 'Направление не указано',
        boxesCount: row.goods_qty_total ?? row.line_count,
        shipmentType: 'FBO' as const,
        title: row.marketplace_label ?? 'FBO',
        source: 'fbo' as const,
      }))
    return [...fbs, ...mp, ...fbo].sort((a, b) => {
      if (a.date !== b.date) return a.date.localeCompare(b.date)
      return `${a.shipmentType}-${a.direction}`.localeCompare(`${b.shipmentType}-${b.direction}`)
    })
  }, [fbsRows, mpUnloadSummaries, outboundSummaries])

  const rowsByDay = useMemo(() => {
    const map = new Map<string, ShipmentCalendarRow[]>()
    for (const row of shipmentRows) {
      const rows = map.get(row.date) ?? []
      rows.push(row)
      map.set(row.date, rows)
    }
    return map
  }, [shipmentRows])

  const openRow = (row: ShipmentCalendarRow) => {
    if (row.source === 'fbs') {
      onOpenFbsSupply(row.id)
      return
    }
    if (row.source === 'mp') {
      onOpenMarketplaceUnload(row.id)
      return
    }
    onOpenOutbound(row.id)
  }

  return (
    <Stack spacing={2.5} data-testid="dashboard" data-task-id="CAL-01">
      <Paper variant="outlined" sx={{ p: 2 }} data-testid="cal-01-screen-title" data-task-id="CAL-01">
        <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ justifyContent: 'space-between', gap: 1.5 }}>
          <Box data-testid="cal-01-title-block" data-task-id="CAL-01">
            <Typography variant="h5" component="h1" sx={{ fontWeight: 800 }} data-testid="cal-01-title" data-task-id="CAL-01">
              Календарь отгрузок
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} data-testid="cal-01-month-controls" data-task-id="CAL-01">
            <IconButton
              size="small"
              aria-label="Предыдущий месяц"
              onClick={() => setMonthOffset((current) => current - 1)}
              data-testid="cal-01-prev-month"
              data-task-id="CAL-01"
            >
              <ChevronLeftIcon fontSize="small" />
            </IconButton>
            <Typography sx={{ minWidth: 180, textAlign: 'center', fontWeight: 750 }} data-testid="cal-01-month-label" data-task-id="CAL-01">
              {monthLabel(visibleMonth)}
            </Typography>
            <IconButton
              size="small"
              aria-label="Следующий месяц"
              onClick={() => setMonthOffset((current) => current + 1)}
              data-testid="cal-01-next-month"
              data-task-id="CAL-01"
            >
              <ChevronRightIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
      </Paper>

      {fbsError ? (
        <Alert severity="warning" data-testid="cal-01-fbs-load-error" data-task-id="CAL-01">
          {fbsError}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ overflow: 'hidden' }} data-testid="ff-week-calendar" data-task-id="CAL-01">
        <Box
          sx={(theme) => ({
            display: 'grid',
            gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
            borderBottom: `1px solid ${theme.palette.divider}`,
          })}
          data-testid="cal-01-weekdays"
          data-task-id="CAL-01"
        >
          {dayLabels.map((label) => (
            <Box key={label} sx={{ px: 1.25, py: 1, bgcolor: 'action.hover' }} data-testid="cal-01-weekday" data-task-id="CAL-01">
              <Typography variant="caption" sx={{ fontWeight: 750 }} data-task-id="CAL-01">
                {label}
              </Typography>
            </Box>
          ))}
        </Box>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
          }}
          data-testid="cal-01-grid"
          data-task-id="CAL-01"
        >
          {days.map((day) => {
            const key = fmtKey(day)
            const dayRows = rowsByDay.get(key) ?? []
            const outsideMonth = day.getMonth() !== visibleMonth.getMonth()
            return (
              <Box
                key={key}
                sx={(theme) => ({
                  minHeight: 132,
                  p: 1,
                  borderRight: `1px solid ${theme.palette.divider}`,
                  borderBottom: `1px solid ${theme.palette.divider}`,
                  bgcolor: outsideMonth ? alpha(theme.palette.action.hover, 0.35) : 'background.paper',
                })}
                data-testid={`cal-01-day-${key}`}
                data-task-id="CAL-01"
              >
                <Typography
                  variant="subtitle2"
                  sx={{ mb: 0.75, fontWeight: 800, color: outsideMonth ? 'text.disabled' : 'text.primary' }}
                  data-testid="cal-01-day-number"
                  data-task-id="CAL-01"
                >
                  {day.getDate()}
                </Typography>
                <Stack spacing={0.5} data-testid={`cal-01-day-rows-${key}`} data-task-id="CAL-01">
                  {dayRows.map((row) => (
                    <Box
                      key={`${row.source}-${row.id}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => openRow(row)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openRow(row)
                        }
                      }}
                      sx={(theme) => ({
                        px: 0.75,
                        py: 0.5,
                        border: `1px solid ${alpha(theme.palette.primary.main, 0.18)}`,
                        borderRadius: 1,
                        cursor: 'pointer',
                        bgcolor: row.shipmentType === 'FBS' ? alpha(theme.palette.success.main, 0.1) : alpha(theme.palette.info.main, 0.1),
                        '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.12) },
                      })}
                      data-testid="cal-01-shipment-row"
                      data-task-id="CAL-01"
                      data-shipment-id={row.id}
                      data-shipment-type={row.shipmentType}
                    >
                      <Typography variant="caption" sx={{ display: 'block', fontWeight: 750, lineHeight: 1.2 }} data-task-id="CAL-01">
                        {row.direction}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.2 }} data-task-id="CAL-01">
                        {row.boxesCount} коробов · {row.shipmentType}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
            )
          })}
        </Box>
      </Paper>

      {fbsBusy ? (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} data-testid="cal-01-loading" data-task-id="CAL-01">
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary" data-task-id="CAL-01">
            Обновляем календарь
          </Typography>
        </Stack>
      ) : null}
    </Stack>
  )
}
