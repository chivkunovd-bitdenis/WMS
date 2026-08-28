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

// Заглушка: среднее меняется от периода и продавца, чтобы было видно, что
// переключатели действительно на что-то влияют.
const HOURS: Record<string, number> = {
  'week:': 6.4,
  'week:s-gor': 4.1,
  'week:s-city': 9.2,
  'week:s-larin': 5.8,
  'month:': 7.9,
  'month:s-gor': 5.2,
  'month:s-city': 11.4,
  'month:s-larin': 6.6,
  'custom:': 7.1,
  'custom:s-gor': 4.8,
  'custom:s-city': 10.3,
  'custom:s-larin': 6.1,
}

const ORDERS: Record<Preset, number> = { week: 412, month: 1780, custom: 963 }

export function FbsMetricScreen() {
  const [preset, setPreset] = useState<Preset>('week')
  const [sellerId, setSellerId] = useState('')
  const [range, setRange] = useState<MoscowDateRangeValue>({
    start: '2026-08-01',
    end: '2026-08-28',
  })

  const hours = HOURS[`${preset}:${sellerId}`] ?? 0
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
              по {ORDERS[preset].toLocaleString('ru-RU')} заказам
              {seller ? ` · ${seller.name}` : ' · все продавцы'}
            </Typography>
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
