import { Paper, Stack, TextField } from '@mui/material'
import type { ReactNode } from 'react'

// Канон R-03: поиск и фильтры всегда в своей «бумаге» над таблицей и всегда
// в одном и том же месте — оператор не ищет фильтр глазами заново на каждом экране.
//
// Три полосы вместо одной, и это не украшение. Когда сканер, фильтры и кнопки
// экрана лежали в общем переносящемся ряду, при нехватке ширины кнопки падали
// вплотную под поле поиска и слипались с ним. Полосы разведены явно, с воздухом
// между ними, поэтому слипнуться нечему при любой ширине окна.
export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = 'Поиск',
  searchHelperText,
  scanner,
  children,
  actions,
  testId,
}: {
  /** Без поиска: на экране, где отбор идёт только выпадающими списками,
      пустое текстовое поле лишь дублирует соседний фильтр. */
  search?: string
  onSearchChange?: (value: string) => void
  searchPlaceholder?: string
  /** Подсказка под полем поиска: чем именно это поле умнее обычного. */
  searchHelperText?: string
  /** Строка сканера — всегда сверху: экран, который слушает сканер, говорит об этом первым. */
  scanner?: ReactNode
  children?: ReactNode
  /** Кнопки экрана — своей полосой справа, а не в общем ряду с фильтрами. */
  actions?: ReactNode
  testId?: string
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid={testId}>
      {scanner ? <Stack sx={{ mb: 2 }}>{scanner}</Stack> : null}
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        sx={{ alignItems: { sm: 'flex-end' }, flexWrap: 'wrap', rowGap: 1.5 }}
      >
        {onSearchChange ? (
          <TextField
            value={search ?? ''}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={searchPlaceholder}
            helperText={searchHelperText}
            sx={{ minWidth: 280 }}
            slotProps={{ htmlInput: { 'data-testid': 'filter-search' } }}
          />
        ) : null}
        {children}
      </Stack>
      {actions ? (
        <Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}>
          {actions}
        </Stack>
      ) : null}
    </Paper>
  )
}
