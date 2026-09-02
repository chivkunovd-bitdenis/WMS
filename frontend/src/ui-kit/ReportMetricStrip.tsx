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
  return value == null ? '—' : `${numberFormatter.format(value)} ${unit}`
}

function formatDelta(delta: NonNullable<ReportMetricItem['delta']>, unit: string) {
  const sign = delta.direction === 'up' ? '+' : delta.direction === 'down' ? '−' : ''
  const deltaUnit = delta.unit === 'quantity' ? unit : '%'
  return `${sign}${numberFormatter.format(Math.abs(delta.value))} ${deltaUnit}`
}

export function ReportMetricStrip({ items, loading = false, testId }: ReportMetricStripProps) {
  // Больше четырёх показателей раскладываем в две строки по три: раньше лишние
  // молча обрезались, и экран показывал не то, что ему передали.
  const columns = items.length > 4 ? 3 : 4
  return (
    <Paper
      variant="outlined"
      sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        overflow: 'hidden',
        mb: 2,
      }}
      data-testid={testId}
      aria-label="Показатели отчёта"
    >
      {items.map((item, index) => {
        const unit = item.unit ?? 'шт.'
        const value = item.moneyMinor !== undefined
          ? formatMoney(item.moneyMinor)
          : formatValue(item.value, unit)
        return (
          <Box
            key={item.key}
            sx={{
              minWidth: 0,
              p: 2,
              borderRight: (index + 1) % columns === 0 ? 0 : 1,
              borderBottom: index < items.length - columns ? 1 : 0,
              borderColor: 'divider',
            }}
            data-testid={testId ? `${testId}-${item.key}` : undefined}
          >
            <Typography variant="body2" color="text.secondary" sx={{ minHeight: 20 }}>
              {item.label}
            </Typography>
            {loading ? (
              <Skeleton
                variant="rounded"
                height={34}
                sx={{ mt: 0.75, ml: 'auto', maxWidth: 150 }}
                data-testid={testId ? `${testId}-${item.key}-skeleton` : undefined}
              />
            ) : (
              <Stack sx={{ alignItems: 'flex-end', mt: 0.5 }}>
                <Typography
                  variant="h6"
                  sx={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right', fontWeight: 700 }}
                >
                  {value}
                </Typography>
                {item.delta ? (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    aria-label={item.delta.a11yLabel}
                    sx={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}
                  >
                    {formatDelta(item.delta, unit)}
                  </Typography>
                ) : null}
                {item.moneyMinor === undefined && item.value === null && !item.delta ? (
                  <Typography variant="caption" color="text.secondary">
                    {item.nullValueLabel ?? 'Недоступно для сравнения'}
                  </Typography>
                ) : null}
              </Stack>
            )}
          </Box>
        )
      })}
    </Paper>
  )
}
