import { Checkbox } from '@mui/material'
import type { FboPrintSelection } from './fboPickPrint'

export function FboPrintCheckbox({ selection, keys, label }: {
  selection: FboPrintSelection
  keys: string[]
  label: string
}) {
  if (!keys.length) return null
  const count = keys.filter((key) => selection.selected.has(key)).length
  return <Checkbox
    size="small"
    checked={count === keys.length}
    indeterminate={count > 0 && count < keys.length}
    slotProps={{ input: { 'aria-label': `Печатать ${label}`, 'aria-checked': count > 0 && count < keys.length ? 'mixed' : count === keys.length } }}
    onClick={(event) => event.stopPropagation()}
    onChange={(_event, checked) => selection.onToggle(keys, checked)}
    sx={{ p: 0.5, flexShrink: 0 }}
  />
}
