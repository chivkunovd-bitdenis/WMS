import { Box, Stack, Tooltip, Typography } from '@mui/material'
import { TARGET_HOURS, hours, type DayPoint } from './speedStub'

// Столбики по дням.
//
// Готового графика в общем наборе нет — там только диаграмма прихода и расхода,
// а она про количество, не про время. Поэтому столбики собраны здесь, но
// нарочно скупо: прямоугольник, подпись, линия норматива. Никаких осей, сеток и
// легенд: на семи днях они добавляют украшений больше, чем смысла.
//
// Показываем медиану, а не среднее. Среднее задирают два-три застрявших заказа,
// и день выглядит провальным, хотя для большинства заказов всё было нормально.
// Среднее и худший лежат рядом в подсказке — чтобы хвост тоже было видно.

const CHART_HEIGHT = 132

export function SpeedBars({ days }: { days: DayPoint[] }) {
  const ceiling = Math.max(TARGET_HOURS * 1.5, ...days.map((day) => day.median)) * 1.1
  const targetOffset = (TARGET_HOURS / ceiling) * CHART_HEIGHT

  return (
    <Box sx={{ position: 'relative', pt: 1, pb: 0.5 }}>
      {/* Линия норматива: глазу нужна опора, иначе столбики не с чем сравнить. */}
      <Box
        sx={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: `${targetOffset + 28}px`,
          borderTop: '1px dashed',
          borderColor: 'warning.main',
          opacity: 0.7,
          pointerEvents: 'none',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          right: 0,
          bottom: `${targetOffset + 30}px`,
          px: 0.75,
          bgcolor: 'background.paper',
          pointerEvents: 'none',
        }}
      >
        <Typography variant="caption" sx={{ color: 'warning.main', fontWeight: 600 }}>
          норматив {TARGET_HOURS} ч
        </Typography>
      </Box>

      <Stack
        direction="row"
        spacing={1.5}
        sx={{ alignItems: 'flex-end', height: CHART_HEIGHT + 28 }}
        data-testid="speed-bars"
      >
        {days.map((day) => {
          const height = Math.max(4, (day.median / ceiling) * CHART_HEIGHT)
          const late = day.median > TARGET_HOURS
          const share = day.orders === 0 ? 0 : Math.round((day.inTime / day.orders) * 100)
          return (
            <Stack key={day.date} sx={{ flex: 1, alignItems: 'center' }} spacing={0.5}>
              <Tooltip
                title={`${day.label}: медиана ${hours(day.median)}, среднее ${hours(day.average)}, самый долгий ${hours(day.worst)}. В срок ${day.inTime} из ${day.orders} — ${share}%`}
              >
                <Stack sx={{ width: '100%', alignItems: 'center' }} spacing={0.5}>
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 700, color: late ? 'error.main' : 'text.primary' }}
                  >
                    {day.median.toFixed(1)}
                  </Typography>
                  <Box
                    sx={{
                      width: '100%',
                      height: `${height}px`,
                      borderRadius: '6px 6px 2px 2px',
                      bgcolor: late ? 'error.main' : 'success.main',
                      opacity: late ? 0.85 : 0.75,
                      transition: 'height 160ms',
                    }}
                    data-testid={`speed-bar-${day.date}`}
                  />
                </Stack>
              </Tooltip>
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                {day.label}
              </Typography>
            </Stack>
          )
        })}
      </Stack>
    </Box>
  )
}
