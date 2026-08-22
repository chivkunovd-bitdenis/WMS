import { Box, Checkbox, Stack, Tooltip, Typography } from '@mui/material'
import type { ReactNode } from 'react'

// Канон R-08: числа выравниваются вправо и набираются табличными цифрами,
// иначе столбец «остаток» перестаёт читаться как столбец.
export function QtyCell({ value, muted = false }: { value: number | null | undefined; muted?: boolean }) {
  return (
    <Typography
      component="span"
      variant="body2"
      sx={{
        fontVariantNumeric: 'tabular-nums',
        color: muted ? 'text.secondary' : 'text.primary',
        fontWeight: muted ? 400 : 600,
      }}
    >
      {value === null || value === undefined ? '—' : value.toLocaleString('ru-RU')}
    </Typography>
  )
}

// Канон R-29: число читается как утверждение. Для превышения — отдельная формулировка,
// а не «2 из 1 короба», которое выглядит как поломка при верных данных.
export function PlanFactCell({ fact, plan }: { fact: number; plan: number }) {
  const over = fact > plan
  return (
    <Tooltip title={over ? `План ${plan}, принято больше на ${fact - plan}` : `План ${plan}`}>
      <Typography
        component="span"
        variant="body2"
        sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: over ? 700 : 500, whiteSpace: 'nowrap' }}
      >
        {over ? `принято ${fact}, план ${plan}` : `${fact} из ${plan}`}
      </Typography>
    </Tooltip>
  )
}

// Канон R-02: длинный текст в ячейке не обрезается молча — под многоточием
// всегда лежит подсказка с полным значением.
export function TextCell({ value, width }: { value: string | null | undefined; width?: number }) {
  const text = value ?? '—'
  return (
    <Tooltip title={text}>
      <Box
        component="span"
        sx={{
          display: 'block',
          maxWidth: width,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {text}
      </Box>
    </Tooltip>
  )
}

// Канон R-10: SKU, артикул продавца, артикул WB и размер — РАЗНЫЕ колонки.
// Склеивать их в одну ячейку запрещено: это прямое требование от 18.08.2026,
// и именно на слипшихся ячейках оператор перестаёт находить нужный артикул.
// Поэтому здесь только фото и SKU — остальное живёт своими колонками.
export function ProductCell({ photo, sku }: { photo?: ReactNode; sku: string }) {
  return (
    <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', minWidth: 0 }}>
      {photo}
      <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
        {sku}
      </Typography>
    </Stack>
  )
}

export type CheckCellProps = {
  checked: boolean
  onChange: (checked: boolean) => void
  ariaLabel: string
  disabledReason?: string
  testId?: string
}

export function CheckCell({ checked, onChange, ariaLabel, disabledReason, testId }: CheckCellProps) {
  const checkbox = (
    <Checkbox
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      slotProps={{ input: { 'aria-label': ariaLabel } }}
      disabled={Boolean(disabledReason)}
      data-testid={testId}
      size="small"
    />
  )
  return disabledReason ? (
    <Tooltip title={disabledReason}>
      <span style={{ display: 'inline-flex' }}>{checkbox}</span>
    </Tooltip>
  ) : checkbox
}
