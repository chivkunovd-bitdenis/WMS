import { Checkbox, FormControlLabel, MenuItem, Tabs, Tab, TextField, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import type { TextFieldProps } from '@mui/material'

// Формы в WMS должны выглядеть одинаково: small, outlined, без самодельных sx
// на каждом экране. Если нужен новый вариант поля — он появляется здесь.

export type SelectOption = {
  value: string
  label: ReactNode
  disabled?: boolean
}

type TextInputProps = Omit<TextFieldProps, 'size' | 'variant'> & {
  testId?: string
}

export function TextInput({ testId, ...rest }: TextInputProps) {
  return (
    <TextField
      fullWidth
      size="small"
      variant="outlined"
      data-testid={testId}
      {...rest}
    />
  )
}

type SelectFieldProps = Omit<TextFieldProps, 'children' | 'onChange' | 'select' | 'size' | 'value' | 'variant'> & {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  testId?: string
}

export function SelectField({ value, options, onChange, testId, ...rest }: SelectFieldProps) {
  return (
    <TextField
      fullWidth
      select
      size="small"
      variant="outlined"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      data-testid={testId}
      {...rest}
    >
      {options.map((option) => (
        <MenuItem key={option.value} value={option.value} disabled={option.disabled}>
          {option.label}
        </MenuItem>
      ))}
    </TextField>
  )
}

export function CheckboxField({
  label,
  checked,
  onChange,
  disabled,
  testId,
}: {
  label: ReactNode
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  testId?: string
}) {
  return (
    <FormControlLabel
      data-testid={testId}
      control={<Checkbox size="small" checked={checked} disabled={disabled} onChange={(_, value) => onChange(value)} />}
      label={
        <Typography variant="body2" component="span">
          {label}
        </Typography>
      }
    />
  )
}

export type TabOption = {
  value: string
  label: ReactNode
  disabled?: boolean
}

export function TabsBar({
  value,
  tabs,
  onChange,
  testId,
}: {
  value: string
  tabs: TabOption[]
  onChange: (value: string) => void
  testId?: string
}) {
  return (
    <Tabs
      value={value}
      onChange={(_, next) => onChange(String(next))}
      variant="scrollable"
      scrollButtons="auto"
      data-testid={testId}
      sx={{ minHeight: 36, '& .MuiTab-root': { minHeight: 36, textTransform: 'none', fontWeight: 600 } }}
    >
      {tabs.map((tab) => (
        <Tab key={tab.value} value={tab.value} label={tab.label} disabled={tab.disabled} />
      ))}
    </Tabs>
  )
}
