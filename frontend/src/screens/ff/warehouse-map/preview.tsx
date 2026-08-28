import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, CssBaseline, Stack, ThemeProvider, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { FfWarehouseMapScreen } from './FfWarehouseMapScreen'
import type { MapRow } from './WarehouseMapRows'
import type { MoveIntent } from './WarehouseMapMoveDialog'
import { addCell, addWarehouse, applyIntent, emptyStubData, noWarehousesStubData, stubData } from './stub'
import type { WarehouseMapData } from './WarehouseMapTypes'
import '../../../index.css'

// Превью экрана без сервера и без входа в систему. Открывается по адресу
// /warehouse-map.html при запущенном `npm run dev` — так картинку можно смотреть
// и щупать, пока сервера под неё ещё нет.
//
// Полоса состояний сверху — это обвязка превью, а не часть экрана. На боевом
// экране её не будет: состояние приходит от сервера, а не выбирается кнопкой.

type PreviewState = 'normal' | 'loading' | 'error' | 'noCells' | 'noWarehouses'

const STATES: Array<{ value: PreviewState; label: string }> = [
  { value: 'normal', label: 'Штатный вид' },
  { value: 'loading', label: 'Грузится' },
  { value: 'error', label: 'Ошибка' },
  { value: 'noCells', label: 'Пусто: нет ячеек' },
  { value: 'noWarehouses', label: 'Пусто: нет складов' },
]

const ACTOR = 'Смирнова Ольга'

export function PreviewHarness() {
  const [state, setState] = useState<PreviewState>('normal')
  const [warehouseId, setWarehouseId] = useState('wh-yartsevo')
  const [data, setData] = useState<WarehouseMapData>(() => stubData('wh-yartsevo'))
  const [note, setNote] = useState<string | null>(null)

  function reload(nextWarehouseId: string) {
    setWarehouseId(nextWarehouseId)
    setData(stubData(nextWarehouseId))
    setNote(null)
  }

  const shown =
    state === 'noWarehouses'
      ? noWarehousesStubData()
      : state === 'noCells'
        ? emptyStubData()
        : data

  function handleMove(intent: MoveIntent, qty: number) {
    setData((current) =>
      applyIntent(
        current,
        {
          reason: intent.reason,
          rowKey: intent.row.key,
          rowTitle: intent.row.title,
          fromLabel: intent.fromLabel,
          toKey: intent.toKey,
          toLabel: intent.toLabel,
        },
        qty,
        ACTOR,
      ),
    )
    setNote(null)
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box
        sx={{
          px: 3,
          py: 1.5,
          bgcolor: 'text.primary',
          color: 'common.white',
        }}
      >
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Лента макета: данные выдуманные, сервера нет. Кнопки ниже показывают, как экран
            выглядит в разных состояниях. На боевом экране этой ленты не будет.
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={state}
            onChange={(_event, value: PreviewState | null) => {
              if (value) {
                setState(value)
                if (value === 'normal') reload(warehouseId)
              }
            }}
            data-testid="preview-state"
          >
            {STATES.map((item) => (
              <ToggleButton
                key={item.value}
                value={item.value}
                sx={{
                  textTransform: 'none',
                  color: 'common.white',
                  borderColor: 'rgba(255,255,255,0.35)',
                  '&.Mui-selected': { color: 'common.white', bgcolor: 'rgba(255,255,255,0.22)' },
                  '&.Mui-selected:hover': { bgcolor: 'rgba(255,255,255,0.3)' },
                }}
                data-testid={`preview-state-${item.value}`}
              >
                {item.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          {note ? (
            <Typography variant="body2" sx={{ opacity: 0.85 }} data-testid="preview-note">
              {note}
            </Typography>
          ) : null}
        </Stack>
      </Box>

      <Box sx={{ display: 'flex' }}>
        {/* Пустая колонка вместо бокового меню: без неё ширина рабочей области
            в макете шире боевой, и масштаб таблицы обманывает. */}
        <Box
          sx={{
            width: 260,
            flexShrink: 0,
            borderRight: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
          <FfWarehouseMapScreen
            data={shown}
            loading={state === 'loading'}
            error={state === 'error' ? 'Не удалось загрузить карту склада. Обновите страницу.' : null}
            warehouseId={state === 'noWarehouses' ? null : warehouseId}
            onWarehouseChange={reload}
            onMove={handleMove}
            onCreateCell={(code) => {
              setData((current) => addCell(current, code))
              setNote(`Заглушка: ячейка ${code} создана только в макете`)
            }}
            onCreateWarehouse={(name) => {
              setData((current) => addWarehouse(current, name))
              setNote(`Заглушка: склад «${name}» создан только в макете`)
            }}
            onPrintCell={(row: MapRow, size) =>
              setNote(`Заглушка: ШК ячейки ${row.title}, этикетка ${size.label} — принтера в макете нет`)
            }
            onInventory={(row: MapRow) =>
              setNote(
                `Откроется инвентаризация по строке «${row.title}» — документ уже наполнен её составом. Экран: /inventory.html`,
              )
            }
            historyFor={(row: MapRow) =>
              shown.journal.filter((entry) => entry.subject === row.title)
            }
          />
        </Box>
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <PreviewHarness />
    </ThemeProvider>
  </StrictMode>,
)
