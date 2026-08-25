import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  sellerHasOzonConnection,
  type ManualProductSeller,
} from './ffManualProductOzon'

type SellerRow = ManualProductSeller
type CreatedProduct = { id: string }

type Props = {
  open: boolean
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  defaultSellerId?: string | null
  onClose: () => void
  onCreated: (product: CreatedProduct) => void | Promise<void>
}

function humanManualProductError(raw: string): string {
  if (raw === 'sku_taken') return 'Такой артикул (SKU) уже есть.'
  if (raw === 'barcode_taken') return 'Такой штрихкод уже занят.'
  if (raw === 'seller_not_found') return 'Селлер не найден.'
  if (raw === 'invalid_dimensions') return 'Укажите все три габарита или оставьте пустыми.'
  if (/^[a-z0-9_:-]+$/i.test(raw.trim())) return 'Не удалось создать товар.'
  return raw || 'Не удалось создать товар.'
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
  const [ozonSku, setOzonSku] = useState('')
  const [ozonOfferId, setOzonOfferId] = useState('')
  const [tz, setTz] = useState('')
  const [lengthMm, setLengthMm] = useState('')
  const [widthMm, setWidthMm] = useState('')
  const [heightMm, setHeightMm] = useState('')
  const [createdProduct, setCreatedProduct] = useState<CreatedProduct | null>(null)
  const ozonConnected = sellerHasOzonConnection(sellers, sellerId)

  useEffect(() => {
    if (open && createdProduct == null) {
      setSellerId(defaultSellerId ?? '')
      setError(null)
    }
  }, [open, defaultSellerId, createdProduct])

  function reset() {
    setError(null)
    setBusy(false)
    setCreatedProduct(null)
    setSellerId(defaultSellerId ?? '')
    setName('')
    setSku('')
    setSize('')
    setBarcode('')
    setVendor('')
    setOzonSku('')
    setOzonOfferId('')
    setTz('')
    setLengthMm('')
    setWidthMm('')
    setHeightMm('')
  }

  function handleClose() {
    if (busy) return
    reset()
    onClose()
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      let created = createdProduct
      if (created == null) {
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

        const body: Record<string, unknown> = {
          name: trimmedName,
          sku_code: trimmedSku,
          seller_id: sellerId,
        }
        if (size.trim()) body.wb_size = size.trim()
        if (barcode.trim()) body.wb_barcode = barcode.trim()
        if (vendor.trim()) body.wb_vendor_code = vendor.trim()
        if (ozonConnected && ozonSku.trim()) body.ozon_sku = ozonSku.trim()
        if (ozonConnected && ozonOfferId.trim()) body.ozon_offer_id = ozonOfferId.trim()
        if (tz.trim()) body.packaging_instructions = tz.trim()
        if (lengthMm.trim()) body.length_mm = Math.floor(Number(lengthMm))
        if (widthMm.trim()) body.width_mm = Math.floor(Number(widthMm))
        if (heightMm.trim()) body.height_mm = Math.floor(Number(heightMm))

        const res = await fetch(apiUrl('/products'), {
          method: 'POST',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!res.ok) {
          const raw = await readApiErrorMessage(res)
          setError(humanManualProductError(raw))
          return
        }
        created = (await res.json()) as CreatedProduct
        setCreatedProduct(created)
      }
      await onCreated(created)
      reset()
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
                onChange={(e) => {
                  setSellerId(String(e.target.value))
                  setOzonSku('')
                  setOzonOfferId('')
                }}
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
            {ozonConnected ? (
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  size="small"
                  label="SKU Ozon"
                  value={ozonSku}
                  onChange={(e) => setOzonSku(e.target.value)}
                  fullWidth
                  slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-ozon-sku' } }}
                />
                <TextField
                  size="small"
                  label="Предложение Ozon"
                  value={ozonOfferId}
                  onChange={(e) => setOzonOfferId(e.target.value)}
                  fullWidth
                  slotProps={{ htmlInput: { 'data-testid': 'ff-manual-product-ozon-offer' } }}
                />
              </Stack>
            ) : null}
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
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                size="small"
                type="number"
                label="Длина, мм"
                value={lengthMm}
                onChange={(e) => setLengthMm(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-manual-product-length' } }}
              />
              <TextField
                size="small"
                type="number"
                label="Ширина, мм"
                value={widthMm}
                onChange={(e) => setWidthMm(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-manual-product-width' } }}
              />
              <TextField
                size="small"
                type="number"
                label="Высота, мм"
                value={heightMm}
                onChange={(e) => setHeightMm(e.target.value)}
                fullWidth
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-manual-product-height' } }}
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} disabled={busy}>
            Отмена
          </Button>
          <Button type="submit" variant="contained" disabled={busy} data-testid="ff-manual-product-submit">
            {createdProduct == null ? 'Создать' : 'Добавить в приёмку'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
