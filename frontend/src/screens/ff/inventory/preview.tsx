import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Box,
  CssBaseline,
  Stack,
  ThemeProvider,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import { muiTheme } from '../../../mui/theme'
import { FfInventoryCountScreen } from './FfInventoryCountScreen'
import { FfInventoryListScreen } from './FfInventoryListScreen'
import { InventoryCreateDialog, type CreateFill } from './InventoryCreateDialog'
import {
  emptyCount,
  noAddressCount,
  postedCount,
  stubCount,
  stubCountForBox,
  stubList,
} from './stub'
import { allProducts, totals } from './InventoryRows'
import type { InventoryCount } from './InventoryTypes'
import '../../../index.css'

// Превью экрана без сервера и без входа в систему. Открывается по адресу
// /inventory.html при запущенном `npm run dev` — картинку можно щупать, пока
// сервера под неё нет.
//
// Полоса состояний сверху — обвязка превью, а не часть экрана. На боевом экране
// её не будет: состояние приходит от сервера, а не выбирается кнопкой.

type PreviewState =
  | 'list'
  | 'draft'
  | 'byBox'
  | 'noAddress'
  | 'posted'
  | 'loading'
  | 'error'
  | 'empty'

const STATES: Array<{ value: PreviewState; label: string }> = [
  { value: 'list', label: 'Список документов' },
  { value: 'draft', label: 'Документ: черновик' },
  { value: 'byBox', label: 'Документ: по коробу' },
  { value: 'noAddress', label: 'Без адресного хранения' },
  { value: 'posted', label: 'Документ: проведён' },
  { value: 'loading', label: 'Грузится' },
  { value: 'error', label: 'Ошибка' },
  { value: 'empty', label: 'Пусто' },
]

export function PreviewHarness() {
  const [state, setState] = useState<PreviewState>('list')
  const [count, setCount] = useState<InventoryCount>(() => stubCount())
  const [byBox, setByBox] = useState<InventoryCount>(() => stubCountForBox())
  const [note, setNote] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  const onList = state === 'list'
  const current =
    state === 'posted'
      ? postedCount()
      : state === 'empty'
        ? emptyCount()
        : state === 'noAddress'
          ? noAddressCount()
          : state === 'byBox'
            ? byBox
            : count

  function update(next: InventoryCount) {
    setNote(null)
    if (state === 'byBox') setByBox(next)
    else setCount(next)
  }

  function handleSave() {
    const t = totals(current)
    setNote(`Сохранено. Посчитано ${t.counted} из ${t.lines}, остатки не тронуты.`)
  }

  function handlePost() {
    const t = totals(current)
    const staleNote =
      t.stale > 0
        ? ` По ${t.stale} строкам остаток успел измениться — посчитано от нового.`
        : ''
    setNote(
      `Проведено: ${t.discrepancies} движений, излишек ${t.surplus}, недостача ${t.shortage}.${staleNote} В превью документ остаётся черновиком.`,
    )
  }

  function handleCreate(warehouse: string, fill: CreateFill, comment: string) {
    const base = stubCount()
    const narrowed = Boolean(fill.seller || fill.category)
    const filtered = !narrowed
      ? base
      : {
          ...base,
          cells: base.cells
            .map((cell) => ({
              ...cell,
              children: cell.children.filter((node) => {
                if (node.kind !== 'product') return true
                if (fill.seller && node.seller !== fill.seller) return false
                if (fill.category && node.category !== fill.category) return false
                return true
              }),
            }))
            .filter((cell) => cell.children.length > 0),
        }
    setCount({
      ...filtered,
      warehouseName: warehouse,
      comment,
      fill: narrowed
        ? { mode: 'filters', seller: fill.seller, category: fill.category }
        : { mode: 'all' },
    })
    setCreateOpen(false)
    setNote(null)
    setState('draft')
  }

  const sellers = [...new Set(allProducts(stubCount()).map((p) => p.seller))]
  const categories = [...new Set(allProducts(stubCount()).map((p) => p.category))]

  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Box sx={{ px: 3, pt: 2 }}>
        <Typography variant="caption" color="text.secondary">
          Превью экрана S-11 «Инвентаризация». Полоса ниже — обвязка превью, на боевом экране её нет.
        </Typography>
        <Stack sx={{ mt: 1, mb: 1 }}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={state}
            onChange={(_, next: PreviewState | null) => {
              if (next) {
                setState(next)
                setNote(null)
              }
            }}
          >
            {STATES.map((item) => (
              <ToggleButton key={item.value} value={item.value}>
                {item.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
      </Box>

      {onList ? (
        <FfInventoryListScreen
          items={stubList()}
          loading={false}
          onOpen={(id) => {
            setNote(null)
            setState(id === 'inv-125' ? 'byBox' : id === 'inv-124' ? 'draft' : 'posted')
          }}
          onCreate={() => setCreateOpen(true)}
        />
      ) : (
        <FfInventoryCountScreen
          count={current}
          loading={state === 'loading'}
          error={state === 'error' ? 'Не удалось загрузить документ. Повторите позже.' : null}
          note={note}
          onChange={update}
          onSave={handleSave}
          onPost={handlePost}
          onCancelDocument={() => setNote('Документ отменён. В превью состояние не меняется.')}
          onBack={() => {
            setNote(null)
            setState('list')
          }}
        />
      )}

      <InventoryCreateDialog
        open={createOpen}
        warehouses={['Ярцево', 'Подольск']}
        sellers={sellers}
        categories={categories}
        onClose={() => setCreateOpen(false)}
        onCreate={handleCreate}
      />
    </ThemeProvider>
  )
}

// Корень React создаётся один раз на страницу.
//
// Вите при горячей перезагрузке заново исполняет этот модуль, и второй
// createRoot на том же узле React отвергает: на экране остаётся старое дерево,
// а клики уходят в никуда. Отладка макета превращается в гадание — «нажал, и
// ничего», хотя код правильный. Поэтому корень запоминаем на самом узле.
type RootHost = HTMLElement & { __previewRoot?: ReturnType<typeof createRoot> }

const container = document.getElementById('root') as RootHost | null
if (container) {
  const root = container.__previewRoot ?? createRoot(container)
  container.__previewRoot = root
  root.render(
    <StrictMode>
      <PreviewHarness />
    </StrictMode>,
  )
}
