import { Paper, Stack, TextField } from '@mui/material'
import type { ReactNode } from 'react'

// Канон R-03: поиск и фильтры всегда в своей «бумаге» над таблицей и всегда
// в одном и том же месте — оператор не ищет фильтр глазами заново на каждом экране.
export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = 'Поиск',
  children,
  testId,
}: {
  search: string
  onSearchChange: (value: string) => void
  searchPlaceholder?: string
  children?: ReactNode
  testId?: string
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid={testId}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap' }}
      >
        <TextField
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={searchPlaceholder}
          sx={{ minWidth: 240 }}
          slotProps={{ htmlInput: { 'data-testid': 'filter-search' } }}
        />
        {children}
      </Stack>
    </Paper>
  )
}
