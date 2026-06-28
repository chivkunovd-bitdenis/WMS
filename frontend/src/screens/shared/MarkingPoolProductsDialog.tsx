import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type ProductOption = {
  id: string
  name: string
  sku_code: string
  seller_id: string | null
}

type LinkedProduct = {
  id: string
  sku_code: string
  name: string
}

type Props = {
  open: boolean
  token: string
  poolId: string
  poolTitle: string
  sellerId: string
  linkedProducts: LinkedProduct[]
  testIdPrefix: string
  onClose: () => void
  onSaved: (products: LinkedProduct[]) => void
  onError?: (message: string | null) => void
}

export function MarkingPoolProductsDialog({
  open,
  token,
  poolId,
  poolTitle,
  sellerId,
  linkedProducts,
  testIdPrefix,
  onClose,
  onSaved,
  onError,
}: Props) {
  const [catalog, setCatalog] = useState<ProductOption[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadBusy, setLoadBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = useMemo(
    () => ({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    }),
    [token],
  )

  const loadCatalog = useCallback(async () => {
    setLoadBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/products'), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const rows = (await res.json()) as ProductOption[]
      setCatalog(rows.filter((row) => row.seller_id === sellerId))
    } finally {
      setLoadBusy(false)
    }
  }, [sellerId, token])

  useEffect(() => {
    if (!open) {
      setSelectedIds(new Set())
      setSearch('')
      setError(null)
      return
    }
    void loadCatalog()
    setSelectedIds(new Set(linkedProducts.map((p) => p.id)))
  }, [open, linkedProducts, loadCatalog])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) {
      return catalog
    }
    return catalog.filter(
      (row) =>
        row.sku_code.toLowerCase().includes(needle) ||
        row.name.toLowerCase().includes(needle),
    )
  }, [catalog, search])

  const toggleProduct = (productId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(productId)) {
        next.delete(productId)
      } else {
        next.add(productId)
      }
      return next
    })
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marking-codes/pools/${poolId}/products`), {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({ product_ids: [...selectedIds] }),
      })
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        setError(message)
        onError?.(message)
        return
      }
      const data = (await res.json()) as { products: LinkedProduct[] }
      onError?.(null)
      onSaved(data.products)
      onClose()
    } finally {
      setBusy(false)
    }
  }

  const selectedChips = catalog.filter((row) => selectedIds.has(row.id))

  return (
    <Dialog
      open={open}
      onClose={() => !busy && onClose()}
      fullWidth
      maxWidth="md"
      data-testid={`${testIdPrefix}-pool-products-dialog`}
    >
      <DialogTitle>Привязать товары — {poolTitle}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Остаток КМ общий на весь пул. Выберите товары селлера, к которым относится этот GTIN.
          </Typography>
          {error ? (
            <Alert severity="error" data-testid={`${testIdPrefix}-pool-products-error`}>
              {error}
            </Alert>
          ) : null}
          {selectedChips.length > 0 ? (
            <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
              {selectedChips.map((row) => (
                <Chip
                  key={row.id}
                  label={row.sku_code}
                  size="small"
                  data-testid={`${testIdPrefix}-pool-product-chip-${row.id}`}
                />
              ))}
            </Stack>
          ) : null}
          <TextField
            label="Поиск"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid={`${testIdPrefix}-pool-products-search`}
          />
          <TableContainer>
            <Table size="small" data-testid={`${testIdPrefix}-pool-products-table`}>
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox" />
                  <TableCell>Артикул</TableCell>
                  <TableCell>Название</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3}>
                      <Typography variant="body2" color="text.secondary">
                        {loadBusy ? 'Загрузка…' : 'Товары не найдены.'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filtered.map((row) => (
                    <TableRow key={row.id} data-testid={`${testIdPrefix}-pool-product-row-${row.id}`}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={selectedIds.has(row.id)}
                          onChange={() => toggleProduct(row.id)}
                          slotProps={{
                            input: {
                              'aria-label': `Выбрать ${row.sku_code}`,
                            },
                          }}
                        />
                      </TableCell>
                      <TableCell>{row.sku_code}</TableCell>
                      <TableCell>{row.name}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={busy || loadBusy}
          onClick={() => void save()}
          data-testid={`${testIdPrefix}-pool-products-save`}
        >
          Сохранить
        </Button>
      </DialogActions>
    </Dialog>
  )
}
