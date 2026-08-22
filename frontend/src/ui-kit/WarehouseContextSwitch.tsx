import { Box, Button, Menu, MenuItem, Typography } from '@mui/material'
import { useState } from 'react'
import { ErrorNotice } from './States'

export type WarehouseOption = { id: string; name: string }

export type WarehouseContextSwitchProps = {
  options: WarehouseOption[]
  value: string | null
  onChange: (warehouseId: string) => void
  loading?: boolean
  disabledReason?: string
  error?: string
  testId?: string
}

export function WarehouseContextSwitch({
  options,
  value,
  onChange,
  loading = false,
  disabledReason,
  error,
  testId,
}: WarehouseContextSwitchProps) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  if (options.length <= 1 && !loading && !error) return null

  const selected = options.find((option) => option.id === value)
  const reason = disabledReason ?? (loading ? 'Загружаем склады' : undefined)
  const disabled = Boolean(reason || error)

  if (error) {
    return <ErrorNotice testId={testId}>{error}</ErrorNotice>
  }

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }} data-testid={testId}>
      <Typography component="span" variant="body2" sx={{ fontWeight: 700, color: 'text.secondary' }}>
        Склад
      </Typography>
      <Button
        variant="outlined"
        size="small"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={Boolean(anchorEl)}
        onClick={(event) => setAnchorEl(event.currentTarget)}
        title={reason}
        data-testid={testId ? `${testId}-button` : undefined}
        sx={{ minWidth: 270, justifyContent: 'space-between', textTransform: 'none', fontWeight: 700 }}
      >
        {loading ? 'Загружаем склады' : selected?.name ?? 'Выберите склад'}
      </Button>
      {reason ? <Typography variant="body2" color="text.secondary">{reason}</Typography> : null}
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
        {options.map((option) => (
          <MenuItem
            key={option.id}
            selected={option.id === value}
            onClick={() => {
              onChange(option.id)
              setAnchorEl(null)
            }}
            data-testid={testId ? `${testId}-option-${option.id}` : undefined}
          >
            {option.name}
          </MenuItem>
        ))}
      </Menu>
    </Box>
  )
}
