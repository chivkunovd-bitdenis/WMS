import { Box, Paper, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { useMemo, useState } from 'react'
import {
  ActionGroup,
  EmptyState,
  PrimaryAction,
  QtyCell,
  ScreenHeader,
  SecondaryAction,
  StatusChip,
} from '../../../../ui-kit'
import { MoveLabPlan } from './MoveLabPlan'
import {
  METRICS,
  advise,
  applyMoves,
  cellQty,
  initialCells,
  itemName,
  type LabAdvice,
  type LabCell,
  type LabMetric,
  type LabMove,
} from './labData'

// «Пульт перемещений» — эксперимент, а не экран системы. Вопрос, на который он
// отвечает: что изменится, если склад перестанет ждать команды и сам скажет, где
// он неудобно разложен. Всё, что здесь есть, считается из данных плана: ни одна
// подсказка не написана руками.

type Timeline = { id: string; text: string; gain: string }

export function MoveLab() {
  const [cells, setCells] = useState<LabCell[]>(() => initialCells())
  const [metric, setMetric] = useState<LabMetric>('fill')
  const [preview, setPreview] = useState<LabAdvice | null>(null)
  const [flying, setFlying] = useState<LabMove[]>([])
  const [timeline, setTimeline] = useState<Timeline[]>([])
  const [selected, setSelected] = useState<LabCell | null>(null)

  const advice = useMemo(() => advise(cells), [cells])
  const legend = METRICS.find((one) => one.value === metric)?.legend ?? ''

  const highlighted = useMemo(() => {
    if (preview) {
      return new Set(preview.moves.flatMap((move) => [move.fromId, move.toId]))
    }
    return new Set(selected ? [selected.id] : [])
  }, [preview, selected])

  function apply(item: LabAdvice) {
    setFlying(item.moves)
    setPreview(item)
    // Сначала летит стрелка, и только потом меняются числа: иначе плитки
    // перекрашиваются раньше, чем глаз успевает понять, что куда поехало.
    window.setTimeout(() => {
      setCells((current) => applyMoves(current, item.moves))
      setTimeline((current) => [{ id: item.id, text: item.title, gain: item.gain }, ...current])
      setFlying([])
      setPreview(null)
    }, 750)
  }

  const totalQty = cells.reduce((sum, cell) => sum + cellQty(cell), 0)
  const busyCells = cells.filter((cell) => cellQty(cell) > 0).length

  return (
    <Box data-testid="move-lab">
      <ScreenHeader
        title="Пульт перемещений"
        purpose="Склад сам говорит, что стоит переложить, и показывает переезд на плане."
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}
        >
          <Stack direction="row" spacing={3} sx={{ alignItems: 'baseline' }}>
            <Stack>
              <Typography variant="h5">{totalQty.toLocaleString('ru-RU')}</Typography>
              <Typography variant="body2" color="text.secondary">
                штук на складе
              </Typography>
            </Stack>
            <Stack>
              <Typography variant="h5">
                {busyCells} из {cells.length}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                ячеек заняты
              </Typography>
            </Stack>
            <Stack>
              <Typography variant="h5">{advice.length}</Typography>
              <Typography variant="body2" color="text.secondary">
                подсказок сейчас
              </Typography>
            </Stack>
          </Stack>
          <Stack spacing={0.75} sx={{ alignItems: { md: 'flex-end' } }}>
            <ToggleButtonGroup
              exclusive
              size="small"
              value={metric}
              onChange={(_event, value: LabMetric | null) => {
                if (value) setMetric(value)
              }}
              data-testid="lab-metric"
            >
              {METRICS.map((one) => (
                <ToggleButton
                  key={one.value}
                  value={one.value}
                  sx={{ textTransform: 'none', fontWeight: 600 }}
                  data-testid={`lab-metric-${one.value}`}
                >
                  {one.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            <Typography variant="body2" color="text.secondary">
              {legend}
            </Typography>
          </Stack>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Paper variant="outlined" sx={{ p: 2, flexGrow: 1, minWidth: 0 }}>
          <MoveLabPlan
            cells={cells}
            metric={metric}
            highlighted={highlighted}
            flying={flying}
            onSelect={(cell) => setSelected((current) => (current?.id === cell.id ? null : cell))}
          />
          {selected ? (
            <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                {selected.code}
              </Typography>
              {cellQty(selected) === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  Ячейка пуста. {selected.distance} шагов от зоны упаковки.
                </Typography>
              ) : (
                <Stack spacing={0.75}>
                  {selected.items.map((entry) => (
                    <Stack
                      key={entry.sku}
                      direction="row"
                      spacing={2}
                      sx={{ justifyContent: 'space-between' }}
                    >
                      <Typography variant="body2">{itemName(entry.sku)}</Typography>
                      <QtyCell value={entry.qty} />
                    </Stack>
                  ))}
                </Stack>
              )}
            </Box>
          ) : null}
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, width: { lg: 420 }, flexShrink: 0 }}>
          <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
            Что стоит переложить
          </Typography>
          {advice.length === 0 ? (
            <EmptyState
              title="Складу нечего предложить"
              hint="Товар собран, ячейки не переполнены, ходовое лежит близко."
            />
          ) : (
            <Stack spacing={1.5}>
              {advice.map((item) => (
                <Paper
                  key={item.id}
                  variant="outlined"
                  sx={{ p: 1.5 }}
                  onMouseEnter={() => setPreview(item)}
                  onMouseLeave={() => setPreview((current) => (current === item ? null : current))}
                  data-testid={`lab-advice-${item.id}`}
                >
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                      <StatusChip label={item.gain} tone={item.tone} />
                    </Stack>
                    <Typography variant="subtitle2">{item.title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {item.reason}
                    </Typography>
                    <ActionGroup>
                      <SecondaryAction
                        onClick={() => setPreview(item)}
                        data-testid={`lab-show-${item.id}`}
                      >
                        Показать
                      </SecondaryAction>
                      <PrimaryAction onClick={() => apply(item)} data-testid={`lab-apply-${item.id}`}>
                        Переложить
                      </PrimaryAction>
                    </ActionGroup>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          )}

          {timeline.length > 0 ? (
            <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                Что уже переложили
              </Typography>
              <Stack spacing={0.75}>
                {timeline.map((entry, index) => (
                  <Stack key={`${entry.id}-${index}`} spacing={0.25}>
                    <Typography variant="body2">{entry.text}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {entry.gain}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Box>
          ) : null}
        </Paper>
      </Stack>
    </Box>
  )
}
