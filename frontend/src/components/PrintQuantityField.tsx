import { useState } from 'react'
import { TextField, type TextFieldProps } from '@mui/material'

export function parsePrintQuantityDraft(raw: string, min: number, max: number): number | null {
  if (!raw.trim()) return null
  const value = Number(raw)
  return Number.isFinite(value) ? Math.max(min, Math.min(max, Math.floor(value))) : null
}

type Props = Omit<TextFieldProps, 'value' | 'onChange' | 'type' | 'onFocus' | 'onBlur'> & {
  value: number
  onChange: (value: number) => void
  min: number
  max: number
}

/** Keep an empty edit visible without changing the last valid print quantity. */
export function PrintQuantityField({ value, onChange, min, max, ...props }: Props) {
  const [draft, setDraft] = useState<string | null>(null)
  return <TextField {...props} type="number" value={draft ?? value}
    onFocus={() => setDraft(String(value))}
    onChange={event => {
      const raw = event.target.value
      setDraft(raw)
      const next = parsePrintQuantityDraft(raw, min, max)
      if (next !== null) onChange(next)
    }}
    onBlur={() => setDraft(null)}
    slotProps={{ htmlInput: { min, max, step: 1 } }}
  />
}
