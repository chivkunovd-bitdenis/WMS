import { Slider, Stack, Typography } from '@mui/material'

// Процентный ползунок с шагом — единственный способ задать долю в системе.
//
// Доля живёт рядом с числом, которое из неё получается: «50%» само по себе
// оператору ничего не говорит, а «50% — это 120 шт из 240 свободных» говорит
// всё. Поэтому число не подпись под ползунком, а его обязательная часть.
export function PercentSlider({
  label,
  value,
  onChange,
  disabled = false,
  disabledReason,
  /** Из чего считается доля — свободный остаток. */
  base,
  step = 10,
  testId,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  disabled?: boolean
  disabledReason?: string
  base: number
  step?: number
  testId?: string
}) {
  const result = Math.floor((base * value) / 100)
  return (
    <Stack spacing={0.5} sx={{ opacity: disabled ? 0.5 : 1 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {value}%
        </Typography>
        <Typography variant="body2" color="text.secondary">
          — это {result.toLocaleString('ru-RU')} шт из {base.toLocaleString('ru-RU')} свободных
        </Typography>
      </Stack>
      <Slider
        value={value}
        onChange={(_event, next) => onChange(Array.isArray(next) ? next[0]! : next)}
        min={0}
        max={100}
        step={step}
        marks
        disabled={disabled}
        valueLabelDisplay="auto"
        aria-label={label}
        data-testid={testId}
        sx={{ mx: 1, width: 'auto' }}
      />
      {disabled && disabledReason ? (
        <Typography variant="caption" color="text.secondary">
          {disabledReason}
        </Typography>
      ) : null}
    </Stack>
  )
}
