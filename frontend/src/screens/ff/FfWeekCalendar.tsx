import { useMemo } from 'react'
import { Box, IconButton, Paper, Stack, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'

export type CalendarInboundBar = {
  id: string
  dateKey: string
  label: string
}

export type CalendarOutboundBar = {
  id: string
  dateKey: string
  label: string
}

function startOfIsoWeekMonday(ref: Date): Date {
  const d = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate())
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  d.setHours(0, 0, 0, 0)
  return d
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

const dayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

type Props = {
  weekOffset: number
  onWeekOffsetChange: (next: number) => void
  inboundBars: CalendarInboundBar[]
  outboundBars: CalendarOutboundBar[]
  onInboundBarClick: (id: string) => void
  onOutboundBarClick: (id: string) => void
}

export function FfWeekCalendar({
  weekOffset,
  onWeekOffsetChange,
  inboundBars,
  outboundBars,
  onInboundBarClick,
  onOutboundBarClick,
}: Props) {
  const weekStart = useMemo(() => {
    const today = new Date()
    const mon = startOfIsoWeekMonday(today)
    return addDays(mon, weekOffset * 7)
  }, [weekOffset])

  const days = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  }, [weekStart])

  const inboundByDay = useMemo(() => {
    const m = new Map<string, CalendarInboundBar[]>()
    for (const b of inboundBars) {
      const arr = m.get(b.dateKey) ?? []
      arr.push(b)
      m.set(b.dateKey, arr)
    }
    return m
  }, [inboundBars])

  const outboundByDay = useMemo(() => {
    const m = new Map<string, CalendarOutboundBar[]>()
    for (const b of outboundBars) {
      const arr = m.get(b.dateKey) ?? []
      arr.push(b)
      m.set(b.dateKey, arr)
    }
    return m
  }, [outboundBars])

  return (
    <Paper
      elevation={0}
      data-testid="ff-week-calendar"
      component="section"
      aria-label="Календарь поставок и отгрузок"
      sx={(theme) => ({
        overflow: 'hidden',
        border: `1px solid ${alpha(theme.palette.primary.main, 0.22)}`,
        borderRadius: 2,
        boxShadow: `0 4px 18px ${alpha(theme.palette.common.black, 0.07)}, 0 1px 3px ${alpha(theme.palette.common.black, 0.05)}`,
      })}
    >
      <Stack
        direction="row"
        sx={(theme) => ({
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2.5,
          py: 2,
          borderBottom: `1px solid ${alpha(theme.palette.divider, 0.95)}`,
          background: `linear-gradient(118deg, ${alpha(theme.palette.primary.main, 0.12)} 0%, ${alpha(theme.palette.primary.light, 0.2)} 48%, ${alpha(theme.palette.primary.main, 0.06)} 100%)`,
        })}
      >
        <Typography
          variant="h6"
          component="h2"
          sx={{
            fontWeight: 800,
            color: 'text.primary',
            letterSpacing: '-0.02em',
            textShadow: '0 1px 0 rgba(255,255,255,0.45)',
          }}
        >
          Неделя
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <IconButton
            size="small"
            aria-label="Предыдущая неделя"
            onClick={() => onWeekOffsetChange(weekOffset - 1)}
            data-testid="ff-calendar-prev-week"
            sx={(theme) => ({
              border: `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              bgcolor: 'background.paper',
            })}
          >
            <ChevronLeftIcon fontSize="small" />
          </IconButton>
          <Typography
            variant="body2"
            sx={{
              minWidth: 168,
              textAlign: 'center',
              fontWeight: 700,
              color: 'text.primary',
              letterSpacing: '0.02em',
            }}
          >
            {fmtKey(days[0]!)} — {fmtKey(days[6]!)}
          </Typography>
          <IconButton
            size="small"
            aria-label="Следующая неделя"
            onClick={() => onWeekOffsetChange(weekOffset + 1)}
            data-testid="ff-calendar-next-week"
            sx={(theme) => ({
              border: `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              bgcolor: 'background.paper',
            })}
          >
            <ChevronRightIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Stack>

      <Stack direction="row" spacing={1} sx={{ alignItems: 'stretch' as const, p: 2, bgcolor: 'background.paper' }}>
        {days.map((d, idx) => {
          const key = fmtKey(d)
          const ins = inboundByDay.get(key) ?? []
          const outs = outboundByDay.get(key) ?? []
          return (
            <Box
              key={key}
              sx={(theme) => ({
                flex: 1,
                minWidth: 0,
                border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                borderRadius: 1.5,
                p: 1.25,
                bgcolor: alpha(theme.palette.primary.main, 0.03),
                minHeight: 220,
                display: 'flex',
                flexDirection: 'column',
                boxShadow: `inset 0 1px 0 ${alpha(theme.palette.common.white, 0.85)}`,
              })}
              data-testid={`ff-calendar-day-${key}`}
            >
              <Typography
                variant="caption"
                sx={{ display: 'block', fontWeight: 700, color: 'text.secondary', letterSpacing: '0.04em' }}
              >
                {dayLabels[idx]}
              </Typography>
              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 800, color: 'text.primary' }}>
                {d.getDate()}.{String(d.getMonth() + 1).padStart(2, '0')}
              </Typography>
              <Stack spacing={0} sx={{ flex: 1, overflow: 'auto' }}>
                {ins.map((b) => (
                  <Box
                    key={`i-${b.id}`}
                    onClick={() => onInboundBarClick(b.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onInboundBarClick(b.id)
                      }
                    }}
                    sx={{
                      py: 0.5,
                      px: 0.75,
                      fontSize: 11,
                      lineHeight: 1.2,
                      cursor: 'pointer',
                      bgcolor: '#fff9c4',
                      color: 'text.primary',
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                      '&:hover': { filter: 'brightness(0.97)' },
                    }}
                    data-testid="ff-cal-inbound-bar"
                    data-doc-id={b.id}
                  >
                    {b.label}
                  </Box>
                ))}
                {outs.map((b) => (
                  <Box
                    key={`o-${b.id}`}
                    onClick={() => onOutboundBarClick(b.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onOutboundBarClick(b.id)
                      }
                    }}
                    sx={{
                      py: 0.5,
                      px: 0.75,
                      fontSize: 11,
                      lineHeight: 1.2,
                      cursor: 'pointer',
                      bgcolor: '#90caf9',
                      color: 'text.primary',
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                      '&:hover': { filter: 'brightness(0.97)' },
                    }}
                    data-testid="ff-cal-outbound-bar"
                    data-doc-id={b.id}
                  >
                    {b.label}
                  </Box>
                ))}
              </Stack>
            </Box>
          )
        })}
      </Stack>

      <Stack
        direction="row"
        spacing={2}
        sx={(theme) => ({
          mt: 0,
          px: 2,
          py: 1.75,
          flexWrap: 'wrap',
          gap: 1.5,
          borderTop: `1px solid ${alpha(theme.palette.divider, 0.95)}`,
          bgcolor: alpha(theme.palette.primary.main, 0.04),
        })}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Box
            sx={(theme) => ({
              width: 16,
              height: 16,
              bgcolor: '#fff59d',
              border: `1px solid ${alpha(theme.palette.common.black, 0.12)}`,
              borderRadius: 0.5,
              boxShadow: `0 1px 2px ${alpha(theme.palette.common.black, 0.08)}`,
            })}
          />
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
            Поставка (план привоза селлером)
          </Typography>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Box
            sx={(theme) => ({
              width: 16,
              height: 16,
              bgcolor: '#64b5f6',
              border: `1px solid ${alpha(theme.palette.common.black, 0.12)}`,
              borderRadius: 0.5,
              boxShadow: `0 1px 2px ${alpha(theme.palette.common.black, 0.08)}`,
            })}
          />
          <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
            Отгрузка на склад МП (запланировано)
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  )
}
