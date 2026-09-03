import { Box, Paper, Skeleton, Stack, Typography } from '@mui/material'
import { formatMoney } from './Cells'

type ReportMetricBase = {
  key: string
  label: string
  delta?: {
    value: number
    direction: 'up' | 'down' | 'flat'
    a11yLabel: string
    unit?: 'percent' | 'quantity'
  }
  nullValueLabel?: string
}

export type ReportMetricItem =
  | (ReportMetricBase & {
    value: number | null
    unit?: string
    moneyMinor?: never
  })
  | (ReportMetricBase & {
    /** Integer minor currency units rendered by the canonical money formatter. */
    moneyMinor: number | string | null
    value?: never
    unit?: never
  })

export type ReportMetricStripProps = {
  items: ReportMetricItem[]
  loading?: boolean
  testId?: string
}

const numberFormatter = new Intl.NumberFormat('ru-RU')

function formatValue(value: number | null | undefined, unit: string) {
  if (value == null) return '—'
  return unit ? `${numberFormatter.format(value)} ${unit}` : numberFormatter.format(value)
}

function formatDelta(delta: NonNullable<ReportMetricItem['delta']>, unit: string) {
  const sign = delta.direction === 'up' ? '+' : delta.direction === 'down' ? '−' : ''
  const deltaUnit = delta.unit === 'quantity' ? unit : '%'
  return `${sign}${numberFormatter.format(Math.abs(delta.value))} ${deltaUnit}`
}

export function ReportMetricStrip({ items, loading = false, testId }: ReportMetricStripProps) {
  // Плашки — отдельные карточки в резиновом ряду, а не жёсткая сетка из четырёх
  // колонок. Жёсткая молча обрезала лишние показатели и растягивала каждый на
  // четверть экрана: подпись жалась влево, число убегало вправо, между ними
  // зияла пустота. Карточка занимает столько, сколько нужно её числу.
  return (
    <Box
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 2 }}
      data-testid={testId}
      aria-label="Показатели отчёта"
    >
      {items.map((item) => {
        const unit = item.unit ?? 'шт.'
        const isMoney = item.moneyMinor !== undefined
        const value = isMoney ? formatMoney(item.moneyMinor) : formatValue(item.value, '')
        return (
          <Paper
            key={item.key}
            variant="outlined"
            sx={{
              // Карточка не тянется на всю ширину: показателю из четырёх цифр
              // четверть экрана не нужна, а лишняя ширина выдавливает соседей
              // за край.
              flex: '1 1 170px',
              minWidth: 165,
              maxWidth: 215,
              px: 2,
              py: 1.5,
              borderRadius: 2,
              borderColor: 'divider',
            }}
            data-testid={testId ? `${testId}-${item.key}` : undefined}
          >
            <Typography
              variant="caption"
              sx={{
                display: 'block',
                color: 'text.secondary',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                fontWeight: 600,
                fontSize: 12,
              }}
            >
              {item.label}
            </Typography>
            {loading ? (
              <Skeleton
                variant="rounded"
                height={32}
                sx={{ mt: 0.75 }}
                data-testid={testId ? `${testId}-${item.key}-skeleton` : undefined}
              />
            ) : (
              <Stack direction="row" spacing={0.75} sx={{ alignItems: 'baseline', mt: 0.5 }}>
                <Typography
                  sx={{
                    fontSize: 24,
                    fontWeight: 700,
                    lineHeight: 1.15,
                    fontVariantNumeric: 'tabular-nums',
                    color: isMoney ? 'primary.main' : 'text.primary',
                  }}
                >
                  {value}
                </Typography>
                {!isMoney && item.value != null ? (
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {unit}
                  </Typography>
                ) : null}
              </Stack>
            )}
            {item.delta && !loading ? (
              <Typography
                variant="caption"
                color="text.secondary"
                aria-label={item.delta.a11yLabel}
                sx={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {formatDelta(item.delta, unit)}
              </Typography>
            ) : null}
            {!loading && !isMoney && item.value == null && !item.delta ? (
              <Typography variant="caption" color="text.secondary">
                {item.nullValueLabel ?? 'Недоступно для сравнения'}
              </Typography>
            ) : null}
          </Paper>
        )
      })}
    </Box>
  )
}
