import { Box, Paper, Stack, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { useMemo, useState } from 'react'
import { PrimaryAction, TextInput } from '../../../ui-kit'
import type { SortCell } from './sortingStub'

// Выбор ячейки, когда ячеек не шесть, а двести.
//
// Стена из двухсот плиток — это не выбор, а поиск глазами, и он медленнее
// выпадающего списка, который мы отсюда и убирали. Поэтому плитками показаны
// только те ячейки, которые сейчас имеют отношение к делу: подсказанные (там
// уже лежит этот товар) и недавние (с ними уже работали в этом документе).
// Остальные двести доступны поиском и сканером — а сканером и есть тот способ,
// которым оператор выбирает полку, стоя перед ней.

const SHOWN_IN_SEARCH = 12
// До двух десятков ячеек список показывается целиком: искать в нём нечего, а
// поле поиска над шестью плитками — лишний элемент, который надо прочитать.
const SHOW_ALL_UP_TO = 24

export function SortingCellPicker({
  cells,
  activeCellId,
  suggestedIds,
  recentIds,
  carried,
  onPick,
  onCreateCell,
}: {
  cells: SortCell[]
  activeCellId: string | null
  /** Ячейки, где уже лежит то, что осталось разложить. */
  suggestedIds: string[]
  /** Ячейки, в которые уже клали в этом документе. */
  recentIds: string[]
  carried: boolean
  onPick: (cellId: string) => void
  onCreateCell: () => void
}) {
  const [query, setQuery] = useState('')
  const byId = useMemo(() => new Map(cells.map((cell) => [cell.id, cell])), [cells])

  const found = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return []
    return cells
      .filter(
        (cell) =>
          cell.code.toLowerCase().includes(needle) || cell.barcode.toLowerCase().includes(needle),
      )
      .slice(0, SHOWN_IN_SEARCH)
  }, [cells, query])

  const suggested = suggestedIds.map((id) => byId.get(id)).filter(Boolean) as SortCell[]
  const recent = recentIds.map((id) => byId.get(id)).filter(Boolean) as SortCell[]
  const small = cells.length <= SHOW_ALL_UP_TO

  if (small) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }} data-testid="sorting-cell-picker">
        <Stack spacing={1.5}>
          <Group
            title="Ячейки склада"
            cells={cells}
            activeCellId={activeCellId}
            carried={carried}
            onPick={onPick}
          />
          <PrimaryAction onClick={onCreateCell} data-testid="sorting-create-cell">
            Создать ячейку
          </PrimaryAction>
        </Stack>
      </Paper>
    )
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="sorting-cell-picker">
      <Stack spacing={1.5}>
        <TextInput
          label="Найти ячейку"
          value={query}
          onChange={setQuery}
          helperText={`На складе ${cells.length} ячеек — ищите по коду или пикните полку`}
          testId="sorting-cell-search"
        />

        {query.trim() ? (
          <Group
            title={found.length > 0 ? `Нашлось: ${found.length}` : 'Ничего не нашлось'}
            cells={found}
            activeCellId={activeCellId}
            carried={carried}
            onPick={onPick}
          />
        ) : (
          <>
            <Group
              title="Туда, где уже лежит"
              cells={suggested}
              activeCellId={activeCellId}
              carried={carried}
              onPick={onPick}
              emptyHint="Для оставшихся строк подсказок нет — товар новый на складе."
            />
            <Group
              title="Недавние"
              cells={recent}
              activeCellId={activeCellId}
              carried={carried}
              onPick={onPick}
              emptyHint="Пока ни в одну ячейку не клали."
            />
          </>
        )}

        <PrimaryAction onClick={onCreateCell} data-testid="sorting-create-cell">
          Создать ячейку
        </PrimaryAction>
      </Stack>
    </Paper>
  )
}

function Group({
  title,
  cells,
  activeCellId,
  carried,
  onPick,
  emptyHint,
}: {
  title: string
  cells: SortCell[]
  activeCellId: string | null
  carried: boolean
  onPick: (cellId: string) => void
  emptyHint?: string
}) {
  const theme = useTheme()
  return (
    <Stack spacing={0.75}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      {cells.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyHint ?? '—'}
        </Typography>
      ) : (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
          {cells.map((cell) => {
            const active = activeCellId === cell.id
            return (
              <Box
                key={cell.id}
                role="button"
                tabIndex={0}
                onClick={() => onPick(cell.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') onPick(cell.id)
                }}
                onDragOver={(event) => {
                  if (carried) event.preventDefault()
                }}
                onDrop={() => onPick(cell.id)}
                data-testid={`sorting-cell-${cell.id}`}
                sx={{
                  px: 1.25,
                  py: 0.6,
                  borderRadius: 2,
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: active ? 'primary.main' : 'divider',
                  backgroundColor: active
                    ? alpha(theme.palette.primary.main, 0.12)
                    : 'background.paper',
                  outline: carried && !active ? `1px dashed ${alpha(theme.palette.primary.main, 0.45)}` : 'none',
                  outlineOffset: '-3px',
                }}
              >
                <Typography variant="body2" sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {cell.code}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {cell.occupied.length === 0
                    ? 'пусто'
                    : `${cell.occupied[0]!.qty} шт`}
                </Typography>
              </Box>
            )
          })}
        </Stack>
      )}
    </Stack>
  )
}
