import { useMemo, useState, type FormEventHandler } from 'react'
import { Link } from 'react-router-dom'
import {
  Alert,
  Box,
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
import { StatusChip, FilterBar, DataTable } from '../../ui-kit/index'
import type { StatusTone, Column } from '../../ui-kit/index'

type LocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = { id: string; name: string; sku_code: string }

// R-12: в общем журнале переносов типы различаются колонкой «Тип» + фильтром.
// R-14/R-16: StatusChip; neutral = нейтральная информация (не проблема, не успех).
export type TransferType = 'manual' | 'auto_pick'

export type TransferRow = {
  id: string
  from_location_code: string | null
  to_location_code: string | null
  from_warehouse_name: string | null
  to_warehouse_name: string | null
  product_name: string
  quantity: number
  transfer_type: TransferType
  supply_id: string | null
  created_at: string
}

type TransferTypeFilter = TransferType | 'all'

function transferTypeLabel(type: TransferType): string {
  if (type === 'auto_pick') return 'Автоперенос при подборе'
  return 'Ручной перенос'
}

// neutral — нейтральная информация; R-16 (синий/нейтральный — не ошибка и не успех).
function transferTypeTone(_type: TransferType): StatusTone {
  return 'neutral'
}

// Статические колонки DataTable — определены вне компонента, не создаются при рендере.
const transferColumns: Column<TransferRow>[] = [
  {
    key: 'type',
    header: 'Тип',
    width: 210,
    // R-14/R-16: StatusChip из ui-kit; neutral = нейтральная информация
    render: (t) => (
      <StatusChip
        label={transferTypeLabel(t.transfer_type)}
        tone={transferTypeTone(t.transfer_type)}
        testId={`transfer-type-chip-${t.id}`}
      />
    ),
  },
  {
    key: 'product',
    header: 'Товар',
    width: 180,
    render: (t) => t.product_name,
  },
  {
    key: 'qty',
    header: 'Кол-во',
    width: 80,
    align: 'right',
    render: (t) => t.quantity,
  },
  {
    key: 'from',
    header: 'Откуда',
    width: 150,
    render: (t) => (
      <>
        <Typography variant="body2">{t.from_location_code ?? '—'}</Typography>
        {t.from_warehouse_name ? (
          <Typography variant="caption" color="text.secondary">
            {t.from_warehouse_name}
          </Typography>
        ) : null}
      </>
    ),
  },
  {
    key: 'to',
    header: 'Куда',
    width: 150,
    render: (t) => (
      <>
        <Typography variant="body2">{t.to_location_code ?? '—'}</Typography>
        {t.to_warehouse_name ? (
          <Typography variant="caption" color="text.secondary">
            {t.to_warehouse_name}
          </Typography>
        ) : null}
      </>
    ),
  },
  {
    key: 'date',
    header: 'Дата',
    width: 130,
    render: (t) => (
      <Typography variant="body2">
        {new Date(t.created_at).toLocaleString('ru-RU', {
          day: '2-digit',
          month: '2-digit',
          year: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })}
      </Typography>
    ),
  },
  // S-25-TC-004: кликабельная ссылка на поставку-источник автопереноса (R-24 — показываем только то, что реально есть)
  {
    key: 'supply',
    header: 'Поставка',
    width: 110,
    render: (t) =>
      t.supply_id ? (
        <Link
          to={`/app/ff/fbs?supply_id=${t.supply_id}`}
          style={{ fontSize: 14 }}
          data-testid={`transfer-supply-link-${t.id}`}
        >
          Открыть
        </Link>
      ) : null,
  },
]

type Props = {
  opsError: string | null
  opsBusy: boolean
  isFulfillmentAdmin: boolean
  locations: LocationRow[]
  products: ProductRow[]
  onStockTransfer: FormEventHandler<HTMLFormElement>
  /** Журнал переносов. Необязателен — если родитель ещё не передаёт, показываем пустое состояние. */
  transfers?: TransferRow[]
}

export function TransfersScreen({
  opsError,
  opsBusy,
  isFulfillmentAdmin,
  locations,
  products,
  onStockTransfer,
  transfers = [],
}: Props) {
  const [fromLoc, setFromLoc] = useState('')
  const [toLoc, setToLoc] = useState('')
  const [productId, setProductId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [typeFilter, setTypeFilter] = useState<TransferTypeFilter>('all')
  const [search, setSearch] = useState('')

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
    onStockTransfer(event)
  }

  const filteredTransfers = useMemo(() => {
    const q = search.trim().toLowerCase()
    return transfers
      .filter((t) => typeFilter === 'all' || t.transfer_type === typeFilter)
      .filter(
        (t) =>
          !q ||
          t.product_name.toLowerCase().includes(q) ||
          (t.from_location_code ?? '').toLowerCase().includes(q) ||
          (t.to_location_code ?? '').toLowerCase().includes(q),
      )
  }, [transfers, typeFilter, search])

  return (
    <Screen title="Перемещения" subtitle="Перемещение товаров между ячейками">
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
                  Переместить {quantityNumber} шт: {productLabel} · {fromLabel} → {toLabel}
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

      {/* R-12: журнал переносов с колонкой «Тип» и фильтром (ручной / автоперенос при подборе) */}
      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
          Журнал переносов
        </Typography>
        {/* FilterBar из ui-kit: поиск + фильтр по типу как child-элемент */}
        <FilterBar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Поиск по товару, ячейке…"
          testId="transfers-filter-bar"
        >
          <FormControl size="small" sx={{ minWidth: 240 }}>
            <InputLabel shrink htmlFor="transfer-type-filter">Тип</InputLabel>
            <NativeSelect
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value as TransferTypeFilter)}
              inputProps={{ id: 'transfer-type-filter', 'data-testid': 'transfer-type-filter' }}
            >
              <option value="all">Все типы</option>
              <option value="manual">Ручной перенос</option>
              <option value="auto_pick">Автоперенос при подборе</option>
            </NativeSelect>
          </FormControl>
        </FilterBar>
        {/* DataTable из ui-kit: R-21 empty state встроен в empty-пропс */}
        <DataTable<TransferRow>
          columns={transferColumns}
          rows={filteredTransfers}
          getRowKey={(t) => t.id}
          testId="transfers-table"
          empty={{
            title: 'Переносов нет',
            hint: 'Создайте перенос кнопкой выше или подождите автоматический перенос при подборе.',
          }}
        />
      </Box>
    </Screen>
  )
}
