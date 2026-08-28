import { Box, Paper, Stack, Typography } from '@mui/material'
import { useMemo, useState } from 'react'
import {
  DataTable,
  FilterBar,
  QtyCell,
  ReportMetricStrip,
  ScreenHeader,
  SelectInput,
  StatusChip,
} from '../../../ui-kit'
import type { Column, ReportMetricItem } from '../../../ui-kit'
import { SpeedBars } from './SpeedBars'
import { SELLER, TARGET_HOURS, WEEK, hours, totals, type DayPoint } from './speedStub'

// Скорость доставки FBS: сколько проходит от прихода заказа к нам до передачи
// его в Wildberries.
//
// Почему медиана, а не среднее. Среднее задирают два-три застрявших заказа, и
// нормальный день выглядит провальным. Медиана отвечает на вопрос «сколько это
// обычно занимает», а среднее и самый долгий стоят рядом и показывают хвост.
// Прятать хвост нельзя: именно из него растут отказы на ПВЗ.

export function FbsSpeedScreen() {
  const [seller, setSeller] = useState(SELLER)
  const days = WEEK
  const week = useMemo(() => totals(days), [days])

  const share = week.orders === 0 ? 0 : Math.round((week.inTime / week.orders) * 100)
  const lateDays = days.filter((day) => day.median > TARGET_HOURS)

  const metrics: ReportMetricItem[] = [
    { key: 'median', label: 'Обычно занимает', value: Number(week.median.toFixed(1)), unit: 'ч' },
    { key: 'avg', label: 'Среднее', value: Number(week.average.toFixed(1)), unit: 'ч' },
    { key: 'worst', label: 'Самый долгий', value: Number(week.worst.toFixed(1)), unit: 'ч' },
    { key: 'orders', label: 'Заказов за неделю', value: week.orders, unit: 'шт' },
  ]

  const columns: Column<DayPoint>[] = [
    {
      key: 'day',
      header: 'День',
      width: 130,
      render: (row) => (
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {row.label}
        </Typography>
      ),
    },
    {
      key: 'orders',
      header: 'Заказов',
      width: 100,
      align: 'right',
      render: (row) => <QtyCell value={row.orders} />,
    },
    {
      key: 'median',
      header: 'Обычно',
      width: 130,
      align: 'right',
      render: (row) => (
        <Typography
          variant="body2"
          sx={{
            fontWeight: 700,
            fontVariantNumeric: 'tabular-nums',
            color: row.median > TARGET_HOURS ? 'error.main' : 'text.primary',
          }}
        >
          {hours(row.median)}
        </Typography>
      ),
    },
    {
      key: 'average',
      header: 'Среднее',
      width: 120,
      align: 'right',
      render: (row) => (
        <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {hours(row.average)}
        </Typography>
      ),
    },
    {
      key: 'worst',
      header: 'Самый долгий',
      width: 140,
      align: 'right',
      render: (row) => (
        <Typography
          variant="body2"
          sx={{
            fontVariantNumeric: 'tabular-nums',
            color: row.worst > TARGET_HOURS * 2 ? 'error.main' : 'text.secondary',
          }}
        >
          {hours(row.worst)}
        </Typography>
      ),
    },
    {
      key: 'inTime',
      header: 'В срок',
      width: 150,
      align: 'right',
      render: (row) => {
        const percent = row.orders === 0 ? 0 : Math.round((row.inTime / row.orders) * 100)
        return (
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'flex-end' }}>
            <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {row.inTime} из {row.orders}
            </Typography>
            <StatusChip
              label={`${percent}%`}
              tone={percent >= 90 ? 'ok' : percent >= 70 ? 'warn' : 'stop'}
              hint={`Уложились в норматив ${TARGET_HOURS} ч`}
            />
          </Stack>
        )
      },
    },
  ]

  return (
    <Box data-testid="fbs-speed-screen">
      <ScreenHeader
        title="Скорость доставки FBS"
        purpose="От прихода заказа к нам до передачи в Wildberries. Медиана отвечает, сколько это занимает обычно; среднее и самый долгий показывают хвост."
      />

      <FilterBar
        testId="fbs-speed-filters"
        actions={
          <StatusChip
            label={`В срок ${share}%`}
            tone={share >= 90 ? 'ok' : share >= 70 ? 'warn' : 'stop'}
            hint={`${week.inTime} заказов из ${week.orders} уложились в ${TARGET_HOURS} часов`}
            testId="fbs-speed-share"
          />
        }
      >
        <Box sx={{ minWidth: 220 }}>
          <SelectInput
            label="Продавец"
            value={seller}
            onChange={setSeller}
            options={[{ value: SELLER, label: SELLER }]}
            testId="fbs-speed-seller"
          />
        </Box>
        <Box sx={{ minWidth: 200 }}>
          <SelectInput
            label="Период"
            value="week"
            onChange={() => undefined}
            options={[{ value: 'week', label: 'Последние 7 дней' }]}
            testId="fbs-speed-period"
          />
        </Box>
      </FilterBar>

      <Paper variant="outlined" sx={{ px: 2.5, pt: 1.5, pb: 1, mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Сколько обычно занимает по дням
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Столбик — медиана дня. Красный означает, что типичный заказ в этот день
          не уложился в норматив.
        </Typography>
        <SpeedBars days={days} />
      </Paper>

      <ReportMetricStrip items={metrics} testId="fbs-speed-metrics" />

      {lateDays.length > 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {lateDays.length === 1 ? 'Не уложился' : 'Не уложились'} {lateDays.length} из{' '}
          {days.length} дней: {lateDays.map((day) => day.label).join(', ')}. Смотрите колонку
          «Самый долгий» — по ней видно, один заказ утянул день или он был таким весь.
        </Typography>
      ) : null}

      <DataTable
        testId="fbs-speed-table"
        columns={columns}
        rows={days}
        getRowKey={(row) => row.date}
        fixedLayout
        hasDiscrepancy={(row) => row.median > TARGET_HOURS}
        empty={{ title: 'За неделю заказов не было', hint: 'Выберите другой период.' }}
      />
    </Box>
  )
}
