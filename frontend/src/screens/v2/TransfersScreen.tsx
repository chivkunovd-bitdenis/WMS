import { useMemo, useState, type FormEventHandler } from 'react'
import {
  Alert,
  Button,
  FormControl,
  InputLabel,
  NativeSelect,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Screen } from '../AppV2Screens'

type LocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = { id: string; name: string; sku_code: string }
type TransferSummary = { quantity: number; product: string; from: string; to: string }

type Props = {
  opsError: string | null
  opsBusy: boolean
  isFulfillmentAdmin: boolean
  locations: LocationRow[]
  products: ProductRow[]
  onStockTransfer: FormEventHandler<HTMLFormElement>
}

export function TransfersScreen({
  opsError,
  opsBusy,
  isFulfillmentAdmin,
  locations,
  products,
  onStockTransfer,
}: Props) {
  const [fromLoc, setFromLoc] = useState('')
  const [toLoc, setToLoc] = useState('')
  const [productId, setProductId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [lastTransfer, setLastTransfer] = useState<TransferSummary | null>(null)

  const fromLabel = useMemo(
    () => locations.find((loc) => loc.id === fromLoc)?.code ?? '',
    [fromLoc, locations],
  )
  const toLabel = useMemo(
    () => locations.find((loc) => loc.id === toLoc)?.code ?? '',
    [toLoc, locations],
  )
  const productLabel = useMemo(() => {
    const p = products.find((row) => row.id === productId)
    return p ? `${p.sku_code} — ${p.name}` : ''
  }, [productId, products])
  const quantityNumber = Number(quantity)
  const sameLocation = Boolean(fromLoc && toLoc && fromLoc === toLoc)
  const quantityInvalid =
    quantity.trim() !== '' &&
    (!Number.isInteger(quantityNumber) || quantityNumber < 1)
  const readyForSubmit =
    Boolean(fromLoc && toLoc && productId) &&
    Number.isInteger(quantityNumber) &&
    quantityNumber > 0 &&
    !sameLocation
  const fromSelectInputProps = {
    id: 'transfer-from-loc',
    name: 'transfer_from_loc',
    'data-testid': 'transfer-from-loc',
    required: true,
  }
  const toSelectInputProps = {
    id: 'transfer-to-loc',
    name: 'transfer_to_loc',
    'data-testid': 'transfer-to-loc',
    required: true,
  }
  const productSelectInputProps = {
    id: 'transfer-product',
    name: 'transfer_product_id',
    'data-testid': 'transfer-product',
    required: true,
  }

  const submit: FormEventHandler<HTMLFormElement> = (event) => {
    if (!readyForSubmit) {
      event.preventDefault()
      return
    }
    setLastTransfer({ quantity: quantityNumber, product: productLabel, from: fromLabel, to: toLabel })
    onStockTransfer(event)
  }

  return (
    <Screen title="Перемещения" subtitle="Перемещение между ячейками на одном складе">
      {opsError ? (
        <Alert severity="error" data-testid="operations-error">
          {opsError}
        </Alert>
      ) : null}
      {!isFulfillmentAdmin ? (
        <Alert severity="info">Доступно только для фулфилмента.</Alert>
      ) : (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid="stock-transfer-section">
          <Stack spacing={2}>
            {lastTransfer ? (
              <Alert severity="success" data-testid="transfer-operation-row">
                Перемещение: {lastTransfer.quantity} шт · {lastTransfer.product} · {lastTransfer.from} → {lastTransfer.to}
              </Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              Выберите товар, ячейку списания и ячейку назначения. Система проведёт расход из первой ячейки и приход во вторую.
            </Typography>
            <Stack
              component="form"
              data-testid="stock-transfer-form"
              noValidate
              onSubmit={submit}
              spacing={2}
            >
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <FormControl
                  fullWidth
                  size="small"
                  required
                >
                  <InputLabel shrink htmlFor="transfer-from-loc">
                    Откуда
                  </InputLabel>
                  <NativeSelect
                    value={fromLoc}
                    onChange={(event) => setFromLoc(event.target.value)}
                    inputProps={fromSelectInputProps}
                  >
                    <option value="" disabled>
                      Выберите ячейку
                    </option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.code}
                      </option>
                    ))}
                  </NativeSelect>
                </FormControl>
                <FormControl
                  fullWidth
                  size="small"
                  required
                  error={sameLocation}
                >
                  <InputLabel shrink htmlFor="transfer-to-loc">
                    Куда
                  </InputLabel>
                  <NativeSelect
                    value={toLoc}
                    onChange={(event) => setToLoc(event.target.value)}
                    inputProps={toSelectInputProps}
                  >
                    <option value="" disabled>
                      Выберите ячейку
                    </option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.code}
                      </option>
                    ))}
                  </NativeSelect>
                  <Typography variant="caption" color={sameLocation ? 'error.main' : 'text.secondary'}>
                    {sameLocation ? 'Выберите другую ячейку назначения.' : ' '}
                  </Typography>
                </FormControl>
              </Stack>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <FormControl
                  fullWidth
                  size="small"
                  required
                >
                  <InputLabel shrink htmlFor="transfer-product">
                    Товар
                  </InputLabel>
                  <NativeSelect
                    value={productId}
                    onChange={(event) => setProductId(event.target.value)}
                    inputProps={productSelectInputProps}
                  >
                    <option value="" disabled>
                      Выберите SKU
                    </option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.sku_code} — {p.name}
                      </option>
                    ))}
                  </NativeSelect>
                </FormControl>
                <TextField
                  fullWidth
                  size="small"
                  label="Количество"
                  name="transfer_qty"
                  type="number"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  required
                  error={quantityInvalid}
                  helperText={quantityInvalid ? 'Введите целое число от 1.' : ' '}
                  slotProps={{
                    htmlInput: {
                      min: 1,
                      step: 1,
                      inputMode: 'numeric',
                      'data-testid': 'transfer-qty',
                    },
                  }}
                />
              </Stack>
              {readyForSubmit ? (
                <Alert severity="info" data-testid="transfer-summary">
                  Перемещение: {quantityNumber} шт · {productLabel} · {fromLabel} → {toLabel}
                </Alert>
              ) : null}
              <Button
                variant="contained"
                type="submit"
                data-testid="transfer-submit"
                disabled={opsBusy || locations.length < 2 || !readyForSubmit}
              >
                {opsBusy ? 'Перемещаем...' : 'Переместить'}
              </Button>
            </Stack>
          </Stack>
        </Paper>
      )}
    </Screen>
  )
}
