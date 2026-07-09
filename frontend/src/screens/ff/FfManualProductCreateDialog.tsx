import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type SellerRow = { id: string; name: string }

type Props = {
  open: boolean
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  defaultSellerId?: string | null
  onClose: () => void
  onCreated: () => void | Promise<void>
}

export function FfManualProductCreateDialog({
  open,
  token,
  authHeaders,
  sellers,
  defaultSellerId,
  onClose,
  onCreated,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sellerId, setSellerId] = useState(defaultSellerId ?? '')
  const [name, setName] = useState('')
  const [sku, setSku] = useState('')
  const [size, setSize] = useState('')
  const [barcode, setBarcode] = useState('')
  const [vendor, setVendor] = useState('')
  const [tz, setTz] = useState('')
  const [lengthMm, setLengthMm] = useState('')
  const [widthMm, setWidthMm] = useState('')
  const [heightMm, setHeightMm] = useState('')
  const [requiresHonestSign, setRequiresHonestSign] = useState(false)

  useEffect(() => {
    if (open) {
      setSellerId(defaultSellerId ?? '')
      setError(null)
    }
  }, [open, defaultSellerId])

  function reset() {
    setError(null)
    setBusy(false)
    setSellerId(defaultSellerId ?? '')
    setName('')
    setSku('')
    setSize('')
    setBarcode('')
    setVendor('')
    setTz('')
    setLengthMm('')
    setWidthMm('')
    setHeightMm('')
    setRequiresHonestSign(false)
  }

  function handleClose() {
    if (busy) return
    reset()
    onClose()
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const trimmedName = name.trim()
    const trimmedSku = sku.trim()
    if (!trimmedName || !trimmedSku) {
      setError('Укажите название и артикул (SKU).')
      return
    }
    if (!sellerId) {
      setError('Выберите селлера.')
      return
    }
    setBusy(true)
    try {
      const body: Record<string, unknown> = {
        name: trimmedName,
        sku_code: trimmedSku,
        seller_id: sellerId,
        requires_honest_sign: requiresHonestSign,
      }
      if (size.trim()) body.wb_size = size.trim()
      if (barcode.trim()) body.wb_barcode = barcode.trim()
      if (vendor.trim()) body.wb_vendor_code = vendor.trim()
      if (tz.trim()) body.packaging_instructions = tz.trim()
      if (lengthMm.trim()) body.length_mm = Number(lengthMm)
      if (widthMm.trim()) body.width_mm = Number(widthMm)
      if (heightMm.trim()) body.height_mm = Number(heightMm)

      const res = await fetch(apiUrl('/products'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const raw = await readApiErrorMessage(res)
        if (raw === 'sku_taken') {
          setError('Такой артикул (SKU) уже есть.')
          return
        }
        if (raw === 'barcode_taken') {
          setError('Такой штрихкод уже занят.')
          return
        }
        if (raw === 'seller_not_found') {
          setError('Селлер не найден.')
          return
        }
        if (raw === 'invalid_dimensions') {
          setError('Укажите все три габарита или оставьте пустыми.')
          return
        }
        setError(raw)
        return
      }
      reset()
      await onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать товар.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm" data-testid="ff-manual-product-dialog">
      <form onSubmit={(e) => void onSubmit(e)}>
        <DialogTitle>Создать товар</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? (
              <Alert severity="error" data-testid="ff-manual-product-error">
                {error}
              </Alert>
            ) : null}
            <FormControl fullWidth size="small" required>
              <InputLabel id="ff-manual-seller-label">Селлер</InputLabel>
              <Select
                labelId="ff-manual-seller-label"
                label="Селлер"
                value={sellerId}
                onChange={(e) => setSellerId(String(e.target.value))}
                data-testid="ff-manual-product-seller"
              >
                {sellers.map((s) => (
                  <MenuItem key={s.id} value={s.id}>
                    {s.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              required
              size="small"
              label="Название"
              value={name}
              onChange={(e) => setName(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-name' } }}
            />
            <TextField
              required
              size="small"
              label="Артикул (SKU)"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-sku' } }}
            />
            <TextField
              size="small"
              label="Артикул продавца"
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-vendor' } }}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                size="small"
                label="Размер"
                value={size}
                onChange={(e) => setSize(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-size' } }}
              />
              <TextField
                size="small"
                label="ШК (этикетка)"
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-barcode' } }}
              />
            </Stack>
            <TextField
              size="small"
              label="ТЗ упаковки"
              multiline
              minRows={3}
              value={tz}
              onChange={(e) => setTz(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-tz' } }}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                size="small"
                label="Длина, мм (необяз.)"
                type="number"
                value={lengthMm}
                onChange={(e) => setLengthMm(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-length', min: 1 } }}
              />
              <TextField
                size="small"
                label="Ширина, мм (необяз.)"
                type="number"
                value={widthMm}
                onChange={(e) => setWidthMm(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-width', min: 1 } }}
              />
              <TextField
                size="small"
                label="Высота, мм (необяз.)"
                type="number"
                value={heightMm}
                onChange={(e) => setHeightMm(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-height', min: 1 } }}
              />
            </Stack>
            <FormControlLabel
              control={
                <Checkbox
                  checked={requiresHonestSign}
                  onChange={(e) => setRequiresHonestSign(e.target.checked)}
                  data-testid="ff-manual-product-cz"
                />
              }
              label="Нужен Честный знак"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} disabled={busy}>
            Отмена
          </Button>
          <Button type="submit" variant="contained" disabled={busy} data-testid="ff-manual-product-submit">
            Создать
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
