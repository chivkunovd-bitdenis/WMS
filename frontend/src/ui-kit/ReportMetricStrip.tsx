import { Box, Paper, Skeleton, Stack, Typography } from '@mui/material'

export type ReportMetricItem = {
  key: string
  label: string
  value: number | null
  unit?: string
  delta?: {
    value: number
    direction: 'up' | 'down' | 'flat'
    a11yLabel: string
  }
}

export type ReportMetricStripProps = {
  items: ReportMetricItem[]
  loading?: boolean
  testId?: string
}

const numberFormatter = new Intl.NumberFormat('ru-RU')

function formatValue(value: number | null, unit: string) {
  return value === null ? '—' : `${numberFormatter.format(value)} ${unit}`
}

function formatDelta(delta: NonNullable<ReportMetricItem['delta']>, unit: string) {
  const sign = delta.direction === 'up' ? '+' : delta.direction === 'down' ? '−' : ''
  return `${sign}${numberFormatter.format(Math.abs(delta.value))} ${unit}`
}

export function ReportMetricStrip({ items, loading = false, testId }: ReportMetricStripProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        overflow: 'hidden',
        mb: 2,
      }}
      data-testid={testId}
      aria-label="Показатели отчёта"
    >
      {items.slice(0, 4).map((item, index) => {
        const unit = item.unit ?? 'шт.'
        return (
          <Box
            key={item.key}
            sx={{
              minWidth: 0,
              p: 2,
              borderRight: index < 3 ? 1 : 0,
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
                  {formatValue(item.value, unit)}
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
              </Stack>
            )}
          </Box>
        )
      })}
    </Paper>
  )
}
