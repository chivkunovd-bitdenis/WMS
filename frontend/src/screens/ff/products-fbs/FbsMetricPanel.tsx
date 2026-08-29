import { Box, Paper, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import {
  MoscowDateRangeInput,
  SelectInput,
  type MoscowDateRangeValue,
} from '../../../ui-kit'

// Среднее время сборки — крупной цифрой над таблицей заказов FBS.
//
// Считается от момента, когда заказ пришёл к нам, до момента, когда оператор
// нажал «Отгрузить». Точка конца — по всей поставке, а не по каждому заказу:
// именно так это и записывается в системе.
//
// Панель ничего не знает про сеть: числа и выбор периода приходят снаружи.
// Так один и тот же блок стоит и в превью на выдуманных числах, и на боевом
// экране заказов — и они не могут разъехаться.

export type MetricPreset = 'week' | 'month' | 'custom'

export const METRIC_PRESETS: Array<{ value: MetricPreset; label: string }> = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'custom', label: 'Свой период' },
]

type Props = {
  hours: number
  orders: number
  /** Доля заказов, уложившихся в 12 часов. Пусто — сервер её ещё не считает. */
  in12: number | null
  /** Доля заказов, уложившихся в сутки. */
  in24: number | null
  sellers: Array<{ id: string; name: string }>
  sellerId: string
  onSellerChange: (id: string) => void
  preset: MetricPreset
  onPresetChange: (preset: MetricPreset) => void
  range: MoscowDateRangeValue
  onRangeChange: (range: MoscowDateRangeValue) => void
  /** Пока считаем — не показываем прошлые числа как свежие. */
  loading?: boolean
  /**
   * Сводка не посчиталась.
   *
   * Показывать в этом случае «0,0 часа» нельзя: ноль часов — это отличный
   * результат, и по нему принимают решения. Честнее сказать, что цифры нет.
   */
  failed?: boolean
}

export function FbsMetricPanel({
  hours,
  orders,
  in12,
  in24,
  sellers,
  sellerId,
  onSellerChange,
  preset,
  onPresetChange,
  range,
  onRangeChange,
  loading,
  failed,
}: Props) {
  const seller = sellers.find((one) => one.id === sellerId) ?? null
  const noValue = failed && !loading
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="fbs-metric">
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={3}
        sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}
      >
        <Stack spacing={0.25}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
            <Typography variant="h3" sx={{ fontWeight: 800 }} data-testid="fbs-metric-value">
              {loading ? '…' : noValue ? '—' : hours.toLocaleString('ru-RU', { minimumFractionDigits: 1 })}
            </Typography>
            <Typography variant="h6" color="text.secondary">
              часа
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {noValue
              ? 'не удалось посчитать: данные недоступны, обновите страницу'
              : 'среднее время сборки: от поступления заказа до нажатия «Отгрузить»'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {seller ? seller.name : 'все продавцы'}
          </Typography>

          <Stack direction="row" spacing={4} sx={{ pt: 1.5, flexWrap: 'wrap' }}>
            <Stack spacing={0.25}>
              <Typography variant="h5" sx={{ fontWeight: 700 }} data-testid="fbs-metric-orders">
                {loading ? '…' : noValue ? '—' : orders.toLocaleString('ru-RU')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                отгружено заказов
              </Typography>
            </Stack>

            {/* Два порога рядом: по ним видно, ровно склад работает или волнами.
                Среднее этого не показывает — оно одинаково и когда все заказы
                идут по двадцать часов, и когда половина за шесть, а половина за
                двое суток. Без окраски в тревожный цвет: число говорит само. */}
            {in12 === null ? null : (
              <Stack spacing={0.25}>
                <Typography variant="h5" sx={{ fontWeight: 700 }} data-testid="fbs-metric-in12">
                  {loading ? '…' : `${in12}%`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  уложились в 12 часов
                </Typography>
              </Stack>
            )}

            {in24 === null ? null : (
              <Stack spacing={0.25}>
                <Typography variant="h5" sx={{ fontWeight: 700 }} data-testid="fbs-metric-in24">
                  {loading ? '…' : `${in24}%`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  уложились в сутки
                </Typography>
              </Stack>
            )}
          </Stack>
        </Stack>

        <Stack spacing={1.5} sx={{ alignItems: { md: 'flex-end' } }}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={preset}
            onChange={(_event, value: MetricPreset | null) => {
              if (value) onPresetChange(value)
            }}
            data-testid="fbs-metric-preset"
          >
            {METRIC_PRESETS.map((one) => (
              <ToggleButton
                key={one.value}
                value={one.value}
                sx={{ textTransform: 'none', fontWeight: 600 }}
                data-testid={`fbs-metric-preset-${one.value}`}
              >
                {one.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          {preset === 'custom' ? (
            <MoscowDateRangeInput
              label="Период"
              value={range}
              onChange={onRangeChange}
              testId="fbs-metric-range"
            />
          ) : null}
          <Box sx={{ minWidth: 220 }}>
            <SelectInput
              label="Продавец"
              value={sellerId}
              onChange={onSellerChange}
              options={sellers.map((one) => ({ value: one.id, label: one.name }))}
              emptyLabel="Все продавцы"
              testId="fbs-metric-seller"
            />
          </Box>
        </Stack>
      </Stack>
    </Paper>
  )
}
