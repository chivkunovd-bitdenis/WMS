import { Button, Paper, Stack, TextField, Tooltip } from '@mui/material'
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

export type ChoiceFilterProps<Value extends string> = {
  value: Value
  options: Array<{ value: Value; label: string }>
  onChange: (value: Value) => void
  ariaLabel: string
  testId?: string
  disabled?: boolean
  disabledReason?: string
}

export function ChoiceFilter<Value extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  testId,
  disabled = false,
  disabledReason,
}: ChoiceFilterProps<Value>) {
  const isDisabled = disabled || Boolean(disabledReason)

  return (
    <Tooltip title={disabledReason ?? ''} disableHoverListener={!disabledReason}>
      <span>
        <Stack
          direction="row"
          spacing={0.5}
          role="group"
          aria-label={ariaLabel}
          aria-disabled={isDisabled}
          data-testid={testId}
          sx={{
            p: 0.5,
            bgcolor: 'action.hover',
            borderRadius: 1,
            flexWrap: 'wrap',
            '& .MuiButton-root.Mui-focusVisible': {
              outline: '2px solid',
              outlineColor: 'primary.main',
              outlineOffset: 2,
            },
          }}
        >
          {options.map((option) => (
            <Button
              key={option.value}
              size="small"
              variant={option.value === value ? 'contained' : 'text'}
              onClick={() => onChange(option.value)}
              disabled={isDisabled}
              aria-pressed={option.value === value}
            >
              {option.label}
            </Button>
          ))}
        </Stack>
      </span>
    </Tooltip>
  )
}
