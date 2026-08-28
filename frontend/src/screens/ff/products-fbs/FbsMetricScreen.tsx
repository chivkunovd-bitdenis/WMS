import { Box, Paper, Typography } from '@mui/material'
import { useState } from 'react'
import { ScreenHeader, type MoscowDateRangeValue } from '../../../ui-kit'
import { FbsMetricPanel } from './FbsMetricPanel'
import { SELLERS } from './stub'

// Среднее время сборки — крупной цифрой над таблицей заказов FBS.
//
// Считается от момента, когда заказ пришёл к нам, до момента, когда оператор
// нажал «Отгрузить». Точка конца — по всей поставке, а не по каждому заказу:
// именно так это и записывается в системе, и именно так владелец и
// сформулировал. Если заказы попали в одну поставку в разное время, конец у них
// общий — это не искажение, а точное соответствие тому, что произошло.

type Preset = 'week' | 'month' | 'custom'

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
  // По умолчанию открываем на ИП Чжоу: макет делался под разбор его цифр, и
  // общий свод сбивает с толку — 12,7 часа по всем продавцам легко принять за
  // цифру Чжоу, у которого на самом деле 22,6.
  const [sellerId, setSellerId] = useState('s-zhou')
  const [range, setRange] = useState<MoscowDateRangeValue>({
    start: '2026-08-01',
    end: '2026-08-28',
  })

  const key = `${preset}:${sellerId}`

  return (
    <Box data-testid="fbs-metric-screen">
      <ScreenHeader
        title="FBS"
        purpose="Сборочные задания Wildberries: новые, в работе и отгруженные."
      />

      <FbsMetricPanel
        hours={HOURS[key] ?? 0}
        orders={ORDERS[key] ?? 0}
        in12={IN_12[key] ?? 0}
        in24={IN_24[key] ?? 0}
        sellers={SELLERS}
        sellerId={sellerId}
        onSellerChange={setSellerId}
        preset={preset}
        onPresetChange={setPreset}
        range={range}
        onRangeChange={setRange}
      />

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="body2" color="text.secondary">
          Ниже — таблица заказов вкладки «Новые». В макете она не воспроизводится: её эталонный
          вид из четырёх колонок уже утверждён и в этой задаче не меняется.
        </Typography>
      </Paper>
    </Box>
  )
}
