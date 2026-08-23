import { Chip, Tooltip } from '@mui/material'
import type { ReactNode } from 'react'

// Единственный способ показать состояние строки или документа.
// Канон R-14/R-16: у цвета ровно три значения, четвёртого не существует.
//   stop — мешает работать или расхождение; warn — внимание, работать можно;
//   ok — закрыто; neutral — просто информация, а не состояние.
export type StatusTone = 'neutral' | 'ok' | 'warn' | 'stop'

const TONE_SX: Record<StatusTone, { bg: string; fg: string }> = {
  neutral: { bg: 'rgba(91, 33, 182, 0.10)', fg: '#4C1D95' },
  ok: { bg: 'rgba(27, 107, 69, 0.12)', fg: '#14603D' },
  warn: { bg: 'rgba(138, 90, 0, 0.14)', fg: '#7A5000' },
  stop: { bg: 'rgba(163, 42, 32, 0.12)', fg: '#8F241B' },
}

type Props = {
  label: ReactNode
  tone?: StatusTone
  hint?: string
  testId?: string
}

export function StatusChip({ label, tone = 'neutral', hint, testId }: Props) {
  const palette = TONE_SX[tone]
  const chip = (
    <Chip
      size="small"
      label={label}
      data-testid={testId}
      sx={{
        fontWeight: 600,
        backgroundColor: palette.bg,
        color: palette.fg,
        '& .MuiChip-label': { px: 1.1 },
      }}
    />
  )
  return hint ? <Tooltip title={hint}>{chip}</Tooltip> : chip
}

// Значок-признак товара: отвечает на вопрос «нужен ли этому товару ЧЗ», то есть
// это свойство, а не состояние процесса и не действие.
// Канон R-34: признак и действие не выглядят одинаково. Если по элементу можно
// что-то сделать (вставить ТЗ, загрузить коды) — это кнопка, а не значок.
// Канон R-35: одна сущность показывается в одном месте. Если ЧЗ уже виден
// в статусе строки («Ждёт ЧЗ»), значка ЧЗ рядом с SKU быть не должно.
export function MarkChip({ code, hint, testId }: { code: string; hint: string; testId?: string }) {
  return (
    <Tooltip title={hint}>
      <Chip
        size="small"
        variant="outlined"
        label={code}
        data-testid={testId}
        sx={{ fontWeight: 700, borderColor: 'rgba(91, 33, 182, 0.35)', color: '#4C1D95' }}
      />
    </Tooltip>
  )
}
