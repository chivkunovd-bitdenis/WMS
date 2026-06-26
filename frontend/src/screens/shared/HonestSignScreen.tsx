import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material'
import UploadFileOutlined from '@mui/icons-material/UploadFileOutlined'
import QrCode2Outlined from '@mui/icons-material/QrCode2Outlined'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { MarkingProductCodesDialog } from './MarkingProductCodesDialog'
import { MarkingPoolProductsPanel } from './MarkingPoolProductsPanel'

export type MarkingInventoryRow = {
  product_id: string
  sku_code: string
  product_name: string
  requires_honest_sign: boolean
  available_count: number
  printed_count: number
}

type Props = {
  token: string
  /** FF admin: filter by seller; seller portal: omit */
  sellerId?: string | null
  sellerIdRequiredForImport?: boolean
  sellers?: { id: string; name: string }[]
  selectedSellerId?: string | null
  onSelectedSellerIdChange?: (id: string | null) => void
  testIdPrefix?: string
  /** T0.4: optional pool link panel (e2e / until T0.7 pool list) */
  poolPreview?: { poolId: string; poolTitle: string; sellerId: string } | null
}

export function HonestSignScreen({
  token,
  sellerId,
  sellerIdRequiredForImport = false,
  sellers = [],
  selectedSellerId = null,
  onSelectedSellerIdChange,
  testIdPrefix = 'honest-sign',
  poolPreview = null,
}: Props) {
  const [rows, setRows] = useState<MarkingInventoryRow[]>([])
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null)
  const [codesDialogProduct, setCodesDialogProduct] = useState<MarkingInventoryRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [importMsg, setImportMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const effectiveSellerId = sellerId ?? selectedSellerId
  const selectedRow = rows.find((r) => r.product_id === selectedProductId) ?? null

  const authHeaders = {
    Authorization: `Bearer ${token}`,
  }

  const loadInventory = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const q =
        effectiveSellerId && !sellerId
          ? `?seller_id=${encodeURIComponent(effectiveSellerId)}`
          : sellerId
            ? ''
            : effectiveSellerId
              ? `?seller_id=${encodeURIComponent(effectiveSellerId)}`
              : ''
      const res = await fetch(apiUrl(`/operations/marking-codes/inventory${q}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { rows: MarkingInventoryRow[] }
      setRows(data.rows)
      setSelectedProductId((prev) =>
        prev && data.rows.some((r) => r.product_id === prev) ? prev : null,
      )
    } finally {
      setBusy(false)
    }
  }, [effectiveSellerId, sellerId, token])

  useEffect(() => {
    if (sellerIdRequiredForImport && !effectiveSellerId) {
      setRows([])
      setSelectedProductId(null)
      return
    }
    void loadInventory()
  }, [effectiveSellerId, loadInventory, sellerIdRequiredForImport])

  useEffect(() => {
    setSelectedProductId(null)
  }, [effectiveSellerId])

  const onPickFile = () => fileRef.current?.click()

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) {
      return
    }
    const importSellerId = sellerId ?? effectiveSellerId
    if (!importSellerId) {
      setError('Выберите селлера для загрузки кодов.')
      return
    }
    if (!selectedProductId) {
      setError('Отметьте товар в таблице — коды будут загружены для него.')
      return
    }
    setBusy(true)
    setError(null)
    setImportMsg(null)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('product_id', selectedProductId)
      if (sellerIdRequiredForImport) {
        form.append('seller_id', importSellerId)
      }
      const res = await fetch(apiUrl('/operations/marking-codes/import'), {
        method: 'POST',
        headers: authHeaders,
        body: form,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as {
        accepted_count: number
        skipped_count: number
        skip_reasons: { reason: string; count: number }[]
      }
      const skipDetails =
        data.skip_reasons.length > 0
          ? ` Пропуск: ${data.skip_reasons.map((r) => `${r.reason} (${r.count})`).join(', ')}.`
          : ''
      const label = selectedRow ? `${selectedRow.sku_code}` : 'товар'
      setImportMsg(
        `Для «${label}» загружено кодов: ${data.accepted_count}. Пропущено: ${data.skipped_count}.${skipDetails}`,
      )
      await loadInventory()
    } finally {
      setBusy(false)
    }
  }

  const toggleProduct = (productId: string) => {
    setSelectedProductId((prev) => (prev === productId ? null : productId))
    setImportMsg(null)
  }

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <PageHeader
        title="Честный знак"
        description="Отметьте товар, загрузите коды (CSV или PDF) — они привяжутся к выбранной строке."
      />
      {sellerIdRequiredForImport && sellers.length > 0 ? (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Селлер:
          </Typography>
          {sellers.map((s) => (
            <Button
              key={s.id}
              size="small"
              variant={selectedSellerId === s.id ? 'contained' : 'outlined'}
              onClick={() => onSelectedSellerIdChange?.(s.id)}
              data-testid={`${testIdPrefix}-seller-${s.id}`}
            >
              {s.name}
            </Button>
          ))}
        </Stack>
      ) : null}
      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}
      {importMsg ? (
        <Alert severity="success" data-testid={`${testIdPrefix}-import-success`}>
          {importMsg}
        </Alert>
      ) : null}
      {poolPreview ? (
        <MarkingPoolProductsPanel
          token={token}
          poolId={poolPreview.poolId}
          poolTitle={poolPreview.poolTitle}
          sellerId={poolPreview.sellerId}
          testIdPrefix={testIdPrefix}
        />
      ) : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.5}
          sx={{ alignItems: { sm: 'center' } }}
        >
          <Box sx={{ flex: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {selectedRow ? (
                <>
                  Загрузка для: <strong>{selectedRow.product_name}</strong> ({selectedRow.sku_code})
                </>
              ) : (
                'Отметьте товар галочкой в таблице ниже.'
              )}
            </Typography>
          </Box>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.txt,.tsv,.pdf"
            hidden
            data-testid={`${testIdPrefix}-file-input`}
            onChange={(ev) => void onFileChange(ev)}
          />
          <Button
            variant="contained"
            startIcon={<UploadFileOutlined />}
            disabled={
              busy ||
              !selectedProductId ||
              (sellerIdRequiredForImport && !effectiveSellerId)
            }
            onClick={onPickFile}
            data-testid={`${testIdPrefix}-upload`}
          >
            Загрузить коды
          </Button>
        </Stack>
      </Paper>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small" data-testid={`${testIdPrefix}-inventory-table`}>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox" />
              <TableCell>Товар</TableCell>
              <TableCell>Артикул</TableCell>
              <TableCell align="right">Нужен ЧЗ</TableCell>
              <TableCell align="right">Доступно</TableCell>
              <TableCell align="right">Напечатано</TableCell>
              <TableCell align="center" padding="checkbox">
                КИЗ
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary">
                    {busy ? 'Загрузка…' : 'Нет товаров у выбранного селлера.'}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow
                  key={r.product_id}
                  selected={selectedProductId === r.product_id}
                  hover
                  data-testid={`${testIdPrefix}-row-${r.product_id}`}
                >
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={selectedProductId === r.product_id}
                      onChange={() => toggleProduct(r.product_id)}
                      slotProps={{
                        input: {
                          'aria-label': `Выбрать ${r.sku_code}`,
                        },
                      }}
                    />
                  </TableCell>
                  <TableCell>{r.product_name}</TableCell>
                  <TableCell>{r.sku_code}</TableCell>
                  <TableCell align="right">{r.requires_honest_sign ? 'Да' : 'Нет'}</TableCell>
                  <TableCell align="right">{r.available_count}</TableCell>
                  <TableCell align="right">{r.printed_count}</TableCell>
                  <TableCell align="center" padding="checkbox">
                    <Tooltip title="Коды и печать">
                      <span>
                        <IconButton
                          size="small"
                          disabled={r.available_count + r.printed_count === 0}
                          onClick={() => setCodesDialogProduct(r)}
                          data-testid={`${testIdPrefix}-view-codes-${r.product_id}`}
                        >
                          <QrCode2Outlined fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <MarkingProductCodesDialog
        open={codesDialogProduct !== null}
        token={token}
        productId={codesDialogProduct?.product_id ?? null}
        productLabel={
          codesDialogProduct
            ? `${codesDialogProduct.sku_code} · ${codesDialogProduct.product_name}`
            : ''
        }
        testIdPrefix={testIdPrefix}
        onClose={() => setCodesDialogProduct(null)}
      />
    </Stack>
  )
}
