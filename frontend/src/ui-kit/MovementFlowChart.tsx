import { Box, Paper, Skeleton, Stack, Typography } from '@mui/material'

export type MovementFlowPoint = {
  date: string
  inbound: number
  outbound: number
  previousOutbound?: number
}

export type MovementFlowChartProps = {
  series: MovementFlowPoint[]
  showPrevious: boolean
  loading?: boolean
  empty?: { title: string; hint: string }
  ariaDescription: string
  testId?: string
}

const chartWidth = 1000
const chartHeight = 180
const chartPadding = { left: 35, right: 20, top: 20, bottom: 15 }

function pointsFor(values: number[], maximum: number) {
  const width = chartWidth - chartPadding.left - chartPadding.right
  const height = chartHeight - chartPadding.top - chartPadding.bottom
  const denominator = Math.max(values.length - 1, 1)

  return values
    .map((value, index) => {
      const x = chartPadding.left + (index / denominator) * width
      const y = chartPadding.top + height - (value / maximum) * height
      return `${x},${y}`
    })
    .join(' ')
}

function LegendItem({ label, tone, dashed = false }: { label: string; tone: 'inbound' | 'outbound' | 'previous'; dashed?: boolean }) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center" component="span">
      <Box
        component="span"
        aria-hidden="true"
        sx={{
          width: 24,
          borderTop: 3,
          borderColor: tone === 'inbound' ? 'success.main' : tone === 'outbound' ? 'primary.main' : 'grey.500',
          borderTopStyle: dashed ? 'dashed' : 'solid',
        }}
      />
      <Typography component="span" variant="body2">
        {label}
      </Typography>
    </Stack>
  )
}

export function MovementFlowChart({
  series,
  showPrevious,
  loading = false,
  empty = { title: 'За выбранный период движений нет', hint: 'Измените период или снимите фильтры.' },
  ariaDescription,
  testId,
}: MovementFlowChartProps) {
  const hasPrevious = showPrevious && series.some((point) => point.previousOutbound !== undefined)
  const hasMovement = series.some(
    (point) =>
      point.inbound !== 0 ||
      point.outbound !== 0 ||
      (hasPrevious && (point.previousOutbound ?? 0) !== 0),
  )
  const values = series.flatMap((point) => [point.inbound, point.outbound, ...(hasPrevious && point.previousOutbound !== undefined ? [point.previousOutbound] : [])])
  const maximum = Math.max(...values, 1)

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid={testId}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        Движение по дням
      </Typography>
      {loading ? (
        <Skeleton variant="rounded" height={180} sx={{ mt: 1 }} data-testid={testId ? `${testId}-skeleton` : undefined} />
      ) : !hasMovement ? (
        <Box sx={{ py: 5, textAlign: 'center' }}>
          <Typography fontWeight={600}>{empty.title}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {empty.hint}
          </Typography>
        </Box>
      ) : (
        <>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 1 }} aria-label="Легенда графика">
            <LegendItem label="Приход" tone="inbound" />
            <LegendItem label="Расход" tone="outbound" />
            {hasPrevious ? <LegendItem label="Расход, прошлый период" tone="previous" dashed /> : null}
          </Stack>
          <Box component="svg" viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none" role="img" aria-label={ariaDescription} sx={{ display: 'block', width: '100%', height: 180, mt: 1 }}>
            {[25, 75, 125, 165].map((y) => <line key={y} x1="35" y1={y} x2="980" y2={y} stroke="#e2e8f0" strokeWidth="1" />)}
            <polyline fill="none" stroke="#247a45" strokeWidth="4" points={pointsFor(series.map((point) => point.inbound), maximum)} />
            <polyline fill="none" stroke="#5b21b6" strokeWidth="4" points={pointsFor(series.map((point) => point.outbound), maximum)} />
            {hasPrevious ? <polyline fill="none" stroke="#94a3b8" strokeWidth="3" strokeDasharray="9 7" points={pointsFor(series.map((point) => point.previousOutbound ?? 0), maximum)} /> : null}
          </Box>
        </>
      )}
    </Paper>
  )
}
