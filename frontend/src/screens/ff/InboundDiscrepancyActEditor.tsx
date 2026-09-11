import { useState } from 'react'
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Line = { id: string; product_name: string; quantity: number }
type Act = { id: string; status: string; lines: Line[] }
type Props = {
  token: string
  requestId: string
  existingActId?: string
  products: Array<{ id: string; product_id: string; product_name: string; sku_code: string }>
  onChanged: () => Promise<void>
}

/** The existing act APIs, opened from the actual reception/sorting document. */
export function InboundDiscrepancyActEditor({ token, requestId, existingActId, products, onChanged }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [act, setAct] = useState<Act | null>(null)
  const [lineId, setLineId] = useState('')
  const [quantity, setQuantity] = useState('-1')
  const [error, setError] = useState<string | null>(null)
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const base = '/operations/discrepancy-acts'
  async function request(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(apiUrl(path), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
    if (!response.ok) throw new Error(await readApiErrorMessage(response))
    return response
  }
  async function show() {
    if (busy) return
    setOpen(true)
    setAct(null)
    setBusy(true)
    setError(null)
    try {
      const response = existingActId
        ? await request(`${base}/${existingActId}`)
        : await request(base, 'POST', { inbound_intake_request_id: requestId })
      const result = await response.json() as { id: string }
      const detail = await request(`${base}/${result.id}`)
      setAct(await detail.json() as Act)
      await onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось открыть акт')
    } finally { setBusy(false) }
  }
  async function mutate(path: string, method: string, body?: unknown) {
    if (!act || busy) return
    setBusy(true)
    setError(null)
    try {
      await request(path, method, body)
      const updated = await request(`${base}/${act.id}`)
      setAct(await updated.json() as Act)
      await onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить акт')
    } finally { setBusy(false) }
  }
  const selected = products.find((product) => product.id === lineId)
  const parsed = Number(quantity)
  const validQuantity = Number.isSafeInteger(parsed) && parsed !== 0 && Math.abs(parsed) <= 1_000_000_000
  return <>
    <Button variant="outlined" disabled={busy} onClick={() => void show()} data-testid={existingActId ? 'ff-inbound-act-edit' : 'ff-inbound-act-create'}>
      {existingActId ? 'Редактировать акт' : 'Создать акт расхождений'}
    </Button>
    <Dialog open={open} onClose={() => { if (!busy) setOpen(false) }} fullWidth maxWidth="sm">
      <DialogTitle>Акт расхождений</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Alert severity="info">Акт относится к открытой приёмке. После утверждения изменится остаток в зоне сортировки её склада. Отрицательное количество списывает товар, положительное добавляет.</Alert>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {act?.lines.map((line) => <Stack direction="row" spacing={1} key={line.id} sx={{ alignItems: 'center' }}>
            <Typography sx={{ flex: 1 }}>{line.product_name}: {line.quantity > 0 ? '+' : ''}{line.quantity}</Typography>
            {act.status === 'draft' ? <Button disabled={busy} onClick={() => void mutate(`${base}/${act.id}/lines/${line.id}`, 'DELETE')}>Удалить</Button> : null}
          </Stack>)}
          {act?.status === 'draft' ? <>
            <TextField select label="Товар приёмки" value={lineId} onChange={(e) => setLineId(e.target.value)} disabled={busy} data-testid="ff-inbound-act-product">
              {products.map((product) => <MenuItem key={product.id} value={product.id}>{product.product_name} · {product.sku_code}</MenuItem>)}
            </TextField>
            <TextField label="Количество со знаком" value={quantity} onChange={(e) => setQuantity(e.target.value)} disabled={busy} error={!validQuantity} data-testid="ff-inbound-act-quantity" />
            <Button disabled={busy || !selected || !validQuantity} onClick={() => selected && void mutate(`${base}/${act.id}/lines`, 'POST', { product_id: selected.product_id, inbound_intake_line_id: selected.id, quantity: parsed })} data-testid="ff-inbound-act-add">Добавить строку</Button>
          </> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setOpen(false)}>Закрыть</Button>
        {act?.status === 'draft' ? <Button variant="contained" disabled={busy || act.lines.length === 0} onClick={() => void mutate(`${base}/${act.id}/submit`, 'POST')} data-testid="ff-inbound-act-submit">Передать на утверждение</Button> : null}
      </DialogActions>
    </Dialog>
  </>
}
