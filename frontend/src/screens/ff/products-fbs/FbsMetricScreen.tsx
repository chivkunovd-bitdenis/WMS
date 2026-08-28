import { Box, Paper, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { useState } from 'react'
import {
  MoscowDateRangeInput,
  ScreenHeader,
  SelectInput,
  type MoscowDateRangeValue,
} from '../../../ui-kit'
import { SELLERS } from './stub'

// Среднее время сборки — крупной цифрой над таблицей заказов FBS.
//
// Считается от момента, когда заказ пришёл к нам, до момента, когда оператор
// нажал «Отгрузить». Точка конца — по всей поставке, а не по каждому заказу:
// именно так это и записывается в системе, и именно так владелец и
// сформулировал. Если заказы попали в одну поставку в разное время, конец у них
// общий — это не искажение, а точное соответствие тому, что произошло.

type Preset = 'week' | 'month' | 'custom'

const PRESETS: Array<{ value: Preset; label: string }> = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'custom', label: 'Свой период' },
]

// ЦИФРЫ НАСТОЯЩИЕ. Сняты с боевой базы 28.08.2026 запросом
// avg(supply.delivered_at − order.created_at_wb) по переданным поставкам.
// Экран к серверу ещё не подключён, поэтому вписаны руками.
const HOURS: Record<string, number> = {
  'week:': 12.7,
  'week:s-zhou': 22.6,
  'month:': 16.8,
  'month:s-zhou': 29.4,
  'custom:': 16.8,
  'custom:s-zhou': 29.4,
}

const ORDERS: Record<string, number> = {
  'week:': 1407,
  'week:s-zhou': 284,
  'month:': 1706,
  'month:s-zhou': 525,
  'custom:': 1706,
  'custom:s-zhou': 525,
}

// Сколько заказов уложилось в 12 и в 24 часа, в процентах.
//
// Два порога, а не один: 12 часов — это «собрали в тот же день», 24 — «собрали
// к следующему». Между ними и видно, работает склад ровно или волнами. Одно
// среднее этого не показывает: у Чжоу оно 22,6 часа, и по нему нельзя понять,
// все заказы такие или половина ушла за шесть часов, а половина за двое суток.
const IN_12: Record<string, number> = {
  'week:': 51, 'week:s-zhou': 27,
  'month:': 44, 'month:s-zhou': 17,
  'custom:': 44, 'custom:s-zhou': 17,
}

const IN_24: Record<string, number> = {
  'week:': 94, 'week:s-zhou': 81,
  'month:': 80, 'month:s-zhou': 49,
  'custom:': 80, 'custom:s-zhou': 49,
}

export function FbsMetricScreen() {
  const [preset, setPreset] = useState<Preset>('week')
  const [sellerId, setSellerId] = useState('')
  const [range, setRange] = useState<MoscowDateRangeValue>({
    start: '2026-08-01',
    end: '2026-08-28',
  })

  const key = `${preset}:${sellerId}`
  const hours = HOURS[key] ?? 0
  const orders = ORDERS[key] ?? 0
  const in12 = IN_12[key] ?? 0
  const in24 = IN_24[key] ?? 0
  const seller = SELLERS.find((one) => one.id === sellerId) ?? null

  return (
    <Box data-testid="fbs-metric-screen">
      <ScreenHeader
        title="FBS"
        purpose="Сборочные задания Wildberries: новые, в работе и отгруженные."
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="fbs-metric">
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={3}
          sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}
        >
          <Stack spacing={0.25}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
              <Typography variant="h3" sx={{ fontWeight: 800 }} data-testid="fbs-metric-value">
                {hours.toLocaleString('ru-RU', { minimumFractionDigits: 1 })}
              </Typography>
              <Typography variant="h6" color="text.secondary">
                часа
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              среднее время сборки: от поступления заказа до нажатия «Отгрузить»
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {seller ? seller.name : 'все продавцы'}
            </Typography>

            <Stack direction="row" spacing={4} sx={{ pt: 1.5, flexWrap: 'wrap' }}>
              <Stack spacing={0.25}>
                <Typography variant="h5" sx={{ fontWeight: 700 }} data-testid="fbs-metric-orders">
                  {orders.toLocaleString('ru-RU')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  отгружено заказов
                </Typography>
              </Stack>

              {/* Два порога рядом: по ним видно, ровно склад работает или волнами.
                  Среднее этого не показывает — оно одинаково и когда все заказы
                  идут по двадцать часов, и когда половина за шесть, а половина
                  за двое суток. */}
              <Stack spacing={0.25}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
                  <Typography
                    variant="h5"
                    sx={{ fontWeight: 700, color: in12 >= 60 ? 'success.main' : 'error.main' }}
                    data-testid="fbs-metric-in12"
                  >
                    {in12}%
                  </Typography>
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  уложились в 12 часов
                </Typography>
              </Stack>

              <Stack spacing={0.25}>
                <Typography
                  variant="h5"
                  sx={{ fontWeight: 700, color: in24 >= 85 ? 'success.main' : 'warning.main' }}
                  data-testid="fbs-metric-in24"
                >
                  {in24}%
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  уложились в сутки
                </Typography>
              </Stack>
            </Stack>
          </Stack>

          <Stack spacing={1.5} sx={{ alignItems: { md: 'flex-end' } }}>
            <ToggleButtonGroup
              exclusive
              size="small"
              value={preset}
              onChange={(_event, value: Preset | null) => {
                if (value) setPreset(value)
              }}
              data-testid="fbs-metric-preset"
            >
              {PRESETS.map((one) => (
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
                onChange={setRange}
                maxDate="2026-12-31"
                testId="fbs-metric-range"
              />
            ) : null}
            <Box sx={{ minWidth: 220 }}>
              <SelectInput
                label="Продавец"
                value={sellerId}
                onChange={setSellerId}
                options={SELLERS.map((one) => ({ value: one.id, label: one.name }))}
                emptyLabel="Все продавцы"
                testId="fbs-metric-seller"
              />
            </Box>
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="body2" color="text.secondary">
          Ниже — таблица заказов вкладки «Новые». В макете она не воспроизводится: её эталонный
          вид из четырёх колонок уже утверждён и в этой задаче не меняется.
        </Typography>
      </Paper>
    </Box>
  )
}
