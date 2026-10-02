import type { MouseEvent } from 'react'
import { ButtonBase, Stack, Tooltip, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import ReportProblemIcon from '@mui/icons-material/ReportProblem'

/** WMS-636: фильтр ленты упаковки WB «Не принятые WB КИЗ». */
export type FbsRejectedKizFilter = { count: number; active: boolean; onToggle: () => void }

/**
 * R1, R2: красный треугольник с числом N — переключатель фильтра. При N = 0 его нет.
 * Как и «− N +» (WMS-633), фокус не забирает: сканер продолжает писать в поле скана.
 */
export function FbsRejectedKizTriangle({ filter }: { filter: FbsRejectedKizFilter }) {
  if (filter.count <= 0) return null
  const color = filter.active ? 'error.contrastText' : 'error.main'
  const keepFocus = (event: MouseEvent) => event.preventDefault()
  return (
    <Tooltip title={`Не принятые WB КИЗ: ${filter.count}`}>
      <ButtonBase
        tabIndex={-1}
        aria-pressed={filter.active}
        aria-label={`Не принятые WB КИЗ: ${filter.count}`}
        onMouseDown={keepFocus}
        onClick={filter.onToggle}
        data-testid="fbs-wb-rejected-kiz-toggle"
        sx={{
          flexShrink: 0, px: 1, py: 0.25, gap: 0.5, borderRadius: 1, border: 2, borderColor: 'error.main',
          bgcolor: (theme) => (filter.active ? theme.palette.error.main : alpha(theme.palette.error.main, 0.08)),
        }}
      >
        <ReportProblemIcon sx={{ color, fontSize: 30 }} />
        <Typography sx={{ color, fontWeight: 800, fontSize: 26, lineHeight: 1 }} data-testid="fbs-wb-rejected-kiz-count">
          {filter.count}
        </Typography>
      </ButtonBase>
    </Tooltip>
  )
}

/** R4: шапка под зелёной строкой во включённом фильтре. */
export function FbsRejectedKizHeader({ count }: { count: number }) {
  return (
    <Stack
      direction="row"
      spacing={1}
      data-testid="fbs-wb-rejected-kiz-header"
      sx={{
        alignItems: 'center', px: 2, py: 1, borderLeft: '4px solid', borderLeftColor: 'error.main',
        bgcolor: (theme) => alpha(theme.palette.error.main, 0.06),
      }}
    >
      <ReportProblemIcon fontSize="small" sx={{ color: 'error.main' }} />
      <Typography variant="body2" sx={{ fontWeight: 700, color: 'error.main' }}>Не принятые WB КИЗ · {count}</Typography>
    </Stack>
  )
}
