import { useState, useSyncExternalStore } from 'react'
import { Box, Button, Chip, Menu, MenuItem, Stack, Typography } from '@mui/material'
import { entryFor, groupedPrint, snapshot, subscribe } from './state'
export function PackingToolbar({supplyIds}: {supplyIds: string[]}) {
  useSyncExternalStore(subscribe,snapshot)
  const [anchor,setAnchor]=useState<HTMLElement|null>(null)
  const [actionSupply,setActionSupply]=useState('')
  const entries=supplyIds.flatMap(id=>{const entry=entryFor(id);return entry?[entry]:[]})
  const total=entries.reduce((sum,entry)=>sum+entry.orders.length,0)
  const selected=entries.reduce((sum,entry)=>sum+entry.orders.filter(order=>entry.selected.has(order.id)).length,0)
  const printed=entries.reduce((sum,entry)=>sum+entry.printed,0)
  const packed=entries.reduce((sum,entry)=>sum+entry.packed,0)
  const scope=entries.find(entry=>entry.id===actionSupply)??entries[0]
  const wbEntries=entries.filter(entry=>entry.marketplace==='wb')
  const verifiable=wbEntries.filter(entry=>entry.editable&&!entry.busy&&entry.codes>0)
  const close=()=>setAnchor(null)
  return <Box sx={{px:2,py:1.75,borderBottom:1,borderColor:'divider'}} data-testid="demo-common-packing-toolbar">
    <Stack direction={{xs:'column',sm:'row'}} spacing={1.5} sx={{justifyContent:'space-between',alignItems:{sm:'center'}}}>
      <Box><Stack direction="row" spacing={1} sx={{alignItems:"center",mb:0.5}}><Typography variant="h6">Упаковка и маркировка</Typography>{entries.length===1&&entries[0].honestSignSkipped?<Chip size="small" color="warning" label="Сдаём без Честного знака" data-testid="fbs-honest-sign-skipped-chip"/>:null}</Stack><Typography variant="body2" color="text.secondary">Напечатано {printed} из {total} · упаковано {packed} из {total} · выбрано {selected}</Typography></Box>
      <Stack direction="row" spacing={1} sx={{flexWrap:'wrap'}}>
        <Button disabled={!total||entries.some(entry=>entry.busy)} onClick={()=>entries.forEach(entry=>entry.select(selected===total?new Set():new Set(entry.orders.map(order=>order.id))))} data-testid="demo-select-all">{selected===total&&total?'Снять выбор':'Выбрать всё'}</Button>
        <Button disabled={!total||entries.some(entry=>entry.busy)} onClick={()=>groupedPrint(entries.map(entry=>({entry,orders:selected?entry.orders.filter(order=>entry.selected.has(order.id)):entry.orders})).filter(group=>group.orders.length))} data-testid="demo-print-group">{selected?`Печать выбранного (${selected})`:`Печать всего (${total})`}</Button>
        {wbEntries.some(entry=>entry.editable)?<Button disabled={!verifiable.length||wbEntries.some(entry=>entry.busy)} onClick={()=>verifiable.forEach(entry=>entry.verify())} data-testid="demo-check-wb">Проверить в WB{entries.length>1?` · все ${wbEntries.length} поставки`:''}</Button>:null}
        <Button onClick={event=>setAnchor(event.currentTarget)} data-testid="demo-more-actions">Действия с поставкой</Button>
      </Stack>
    </Stack>
    <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={close}>
      {entries.length>1?entries.map(entry=><MenuItem key={entry.id} selected={scope?.id===entry.id} onClick={()=>setActionSupply(entry.id)} sx={{fontWeight:scope?.id===entry.id?700:400,whiteSpace:'normal',maxWidth:440}}>{entry.title} · {entry.seller}</MenuItem>):null}
      {scope?<MenuItem disabled sx={{whiteSpace:'normal',maxWidth:440}}>Действия: {scope.title} · {scope.seller}</MenuItem>:null}
      <MenuItem disabled={!scope||scope.packAllDisabled} onClick={()=>{close();scope?.packAll()}}>Всё упаковано · вся поставка</MenuItem>
      {scope&&!scope.honestSignSkipped&&scope.orders.length>0?<MenuItem disabled={!scope.editable||scope.skipBusy||scope.busy} onClick={()=>{close();scope.skip()}}>Сдать без Честного знака · вся поставка</MenuItem>:null}
      {scope?.marketplace==='wb'?<>
        {entries.length>1&&scope.editable?<MenuItem disabled={scope.busy||scope.codes===0} onClick={()=>{close();scope.verify()}}>Проверить в WB · эта поставка</MenuItem>:null}
        {scope.selected.size>0?<MenuItem disabled={!scope.editable||scope.busy} onClick={()=>{close();scope.transfer()}}>Перенести выбранные ({scope.selected.size}) · из этой поставки</MenuItem>:null}
        {scope.selected.size>0?<MenuItem disabled={!scope.editable||scope.busy||scope.clearable===0} onClick={()=>{close();scope.clear()}}>Очистить ЧЗ выбранных ({scope.selected.size})</MenuItem>:null}
      </>:null}
    </Menu>
  </Box>
}
