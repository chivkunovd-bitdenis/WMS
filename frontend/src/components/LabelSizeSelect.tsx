import { MenuItem, TextField } from '@mui/material'
import {
  LABEL_SIZES,
  resolveLabelSize,
  saveLabelSizeId,
  type LabelSize,
  type LabelSizeId,
} from '../utils/labelSize'

type Props = {
  value: LabelSizeId
  onChange: (size: LabelSize) => void
  disabled?: boolean
  /** Запоминать выбор в localStorage (последний размер между печатями). */
  persist?: boolean
  testId?: string
}

/** Единый выбор физического размера этикетки для всех модалок печати. */
export function LabelSizeSelect({
  value,
  onChange,
  disabled = false,
  persist = true,
  testId = 'label-size-select',
}: Props) {
  return (
    <TextField
      select
      size="small"
      label="Размер этикетки"
      value={value}
      disabled={disabled}
      onChange={(e) => {
        const nextId = e.target.value as LabelSizeId
        if (persist) {
          saveLabelSizeId(nextId)
        }
        onChange(resolveLabelSize(nextId))
      }}
      slotProps={{ htmlInput: { 'data-testid': `${testId}-input` } }}
      data-testid={testId}
      sx={{ minWidth: 180 }}
    >
      {LABEL_SIZES.map((size) => (
        <MenuItem key={size.id} value={size.id} data-testid={`${testId}-option-${size.id}`}>
          {size.label}
        </MenuItem>
      ))}
    </TextField>
  )
}
