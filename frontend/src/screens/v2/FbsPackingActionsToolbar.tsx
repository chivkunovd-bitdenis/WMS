import { useEffect, useRef, useState } from 'react'
import { Box, Button, Chip, Menu, MenuItem, Stack, Typography } from '@mui/material'

/** A supply owns its selection and actions; the toolbar only combines their scope. */
export type FbsPackingActions = {
  id: string
  title: string
  seller: string
  marketplace: 'wb' | 'ozon'
  orderIds: string[]
  selectedIds: string[]
  printed: number
  packed: number
  packedTotal: number
  busy: boolean
  editable: boolean
  codes: number
  clearable: number
  honestSignSkipped: boolean
  skipBusy: boolean
  packAllDisabled: boolean
  select: (ids: string[]) => void
  print: (ids: string[], onClose: (completed: boolean) => void) => boolean
  verify: () => void
  packAll: () => void
  skip: () => void
  transfer: () => void
  clear: () => void
}

type Props = { entries: FbsPackingActions[]; active: boolean; contextKey: string }

export function FbsPackingActionsToolbar({ entries, active, contextKey }: Props) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const [actionSupply, setActionSupply] = useState('')
  const [printing, setPrinting] = useState(false)
  const generation = useRef(0)
  const entriesRef = useRef(entries)
  entriesRef.current = entries
  useEffect(() => {
    generation.current += 1
    setPrinting(false)
    setAnchor(null)
    return () => { generation.current += 1 }
  }, [active, contextKey])

  const total = entries.reduce((sum, entry) => sum + entry.orderIds.length, 0)
  const selected = entries.reduce((sum, entry) => sum + entry.selectedIds.length, 0)
  const printed = entries.reduce((sum, entry) => sum + entry.printed, 0)
  const packed = entries.reduce((sum, entry) => sum + entry.packed, 0)
  const packedTotal = entries.reduce((sum, entry) => sum + entry.packedTotal, 0)
  const scope = entries.find(entry => entry.id === actionSupply) ?? entries[0]
  const wbEntries = entries.filter(entry => entry.marketplace === 'wb')
  const verifiable = wbEntries.filter(entry => entry.editable && !entry.busy && entry.codes > 0)
  const busy = entries.some(entry => entry.busy)
  const scopeLabel = (entry: FbsPackingActions) => `${entry.title} · ${entry.marketplace === 'wb' ? 'WB' : 'Ozon'} · ${entry.seller}`

  const print = () => {
    if (printing || !active) return
    // Freeze identity and order, but obtain each callback from its current supply.
    // No automatic retry or persisted queue: cancelling/reloading stops the batch.
    const queue = entries.map(entry => ({
      id: entry.id,
      ids: [...(selected ? entry.selectedIds : entry.orderIds)],
    })).filter(group => group.ids.length > 0)
    const currentGeneration = ++generation.current
    setPrinting(true)
    const advance = () => {
      if (generation.current !== currentGeneration) return
      const group = queue.shift()
      if (!group) { setPrinting(false); return }
      const entry = entriesRef.current.find(item => item.id === group.id)
      let closed = false
      const opened = entry?.print(group.ids, completed => {
        if (closed || generation.current !== currentGeneration) return
        closed = true
        if (completed) advance()
        else { generation.current += 1; setPrinting(false) }
      })
      if (!opened) { generation.current += 1; setPrinting(false) }
    }
    advance()
  }

  return <Box sx={{ px: 2, py: 1.75, borderBottom: 1, borderColor: 'divider' }} data-testid="fbs-packing-actions">
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
      <Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
          <Typography variant="h6">Упаковка и маркировка</Typography>
          {entries.length === 1 && entries[0].honestSignSkipped ? <Chip size="small" color="warning" label="Сдаём без Честного знака" data-testid="fbs-honest-sign-skipped-chip" /> : null}
        </Stack>
        <Typography variant="body2" color="text.secondary">Напечатано {printed} из {total} · упаковано {packed} из {packedTotal} · выбрано {selected}</Typography>
      </Box>
      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
        <Button disabled={!total || busy || printing} onClick={() => entries.forEach(entry => entry.select(selected === total ? [] : entry.orderIds))} data-testid="fbs-packing-select-all">{selected === total && total ? 'Снять выбор' : 'Выбрать всё'}</Button>
        <Button disabled={!total || busy || printing} onClick={print} data-task-id="FBS-21" data-testid="fbs-packing-print">{selected ? `Печать выбранного (${selected})` : `Печать всего (${total})`}</Button>
        {wbEntries.some(entry => entry.editable) ? <Button disabled={!verifiable.length || wbEntries.some(entry => entry.busy)} onClick={() => verifiable.forEach(entry => entry.verify())} data-testid="fbs-packing-check-wb">Проверить в WB{entries.length > 1 ? ` · все ${wbEntries.length} поставки` : ''}</Button> : null}
        <Button disabled={!entries.length} onClick={event => setAnchor(event.currentTarget)} data-testid="fbs-packing-more-actions">Действия с поставкой</Button>
      </Stack>
    </Stack>
    <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
      {entries.length > 1 ? entries.map(entry => <MenuItem key={entry.id} selected={scope?.id === entry.id} onClick={() => setActionSupply(entry.id)} sx={{ fontWeight: scope?.id === entry.id ? 700 : 400, whiteSpace: 'normal', maxWidth: 440 }}>{scopeLabel(entry)}</MenuItem>) : null}
      {scope ? <MenuItem disabled sx={{ whiteSpace: 'normal', maxWidth: 440 }}>Действия: {scopeLabel(scope)}</MenuItem> : null}
      <MenuItem disabled={!scope || scope.packAllDisabled} onClick={() => { setAnchor(null); scope?.packAll() }}>Всё упаковано · вся поставка</MenuItem>
      {scope && !scope.honestSignSkipped && scope.orderIds.length > 0 ? <MenuItem disabled={!scope.editable || scope.skipBusy || scope.busy} onClick={() => { setAnchor(null); scope.skip() }} data-testid="fbs-skip-honest-sign">Сдать без Честного знака · вся поставка</MenuItem> : null}
      {scope?.marketplace === 'wb' ? <>
        {entries.length > 1 && scope.editable ? <MenuItem disabled={scope.busy || scope.codes === 0} onClick={() => { setAnchor(null); scope.verify() }}>Проверить в WB · эта поставка</MenuItem> : null}
        {scope.selectedIds.length > 0 ? <MenuItem disabled={!scope.editable || scope.busy} onClick={() => { setAnchor(null); scope.transfer() }} data-testid="fbs-packing-transfer-supply">Перенести выбранные ({scope.selectedIds.length}) · из этой поставки</MenuItem> : null}
        {scope.selectedIds.length > 0 ? <MenuItem disabled={!scope.editable || scope.busy || scope.clearable === 0} onClick={() => { setAnchor(null); scope.clear() }} data-testid="fbs-packing-clear-selected">Очистить ЧЗ выбранных ({scope.selectedIds.length})</MenuItem> : null}
      </> : null}
    </Menu>
  </Box>
}
