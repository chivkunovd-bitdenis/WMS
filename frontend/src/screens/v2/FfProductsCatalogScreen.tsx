import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Badge,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import QrCode2OutlinedIcon from '@mui/icons-material/QrCode2Outlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { ProductBarcodeCell } from '../../components/ProductBarcodeCell'
import { ProductBarcodePrintButton } from '../../components/ProductBarcodePrintButton'
import { FfProductMarkingPrintProvider } from '../../components/FfProductMarkingPrintProvider'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { printPackagingInstructions } from '../../utils/printPackagingInstructions'
import {
  catalogRowToDisplayMeta,
  resolveProductPrimaryBarcode,
} from '../../types/wbProductCatalog'
import { FfManualProductCreateDialog } from '../ff/FfManualProductCreateDialog'
import { FfProductTzImportDialog } from '../ff/FfProductTzImportDialog'
import { FfSellerCreateDialog } from '../ff/FfSellerCreateDialog'

type SellerRow = { id: string; name: string }

type FfCatalogRow = {
  id: string
  seller_id: string | null
  seller_name: string | null
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  wb_color: string | null
  wb_brand: string | null
  wb_composition: string | null
  packaging_instructions: string | null
  requires_honest_sign: boolean
  has_packaging_instructions: boolean
  marking_available_count?: number
  is_manual?: boolean
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  onSellersChanged?: () => void | Promise<void>
  canManageCatalog?: boolean
}

function rowMatchesSearch(row: FfCatalogRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return (
    row.name.toLowerCase().includes(needle) ||
    row.sku_code.toLowerCase().includes(needle) ||
    (row.wb_vendor_code?.toLowerCase().includes(needle) ?? false) ||
    (row.wb_nm_id != null && String(row.wb_nm_id).includes(needle)) ||
    (row.wb_size?.toLowerCase().includes(needle) ?? false) ||
    (row.wb_color?.toLowerCase().includes(needle) ?? false) ||
    (row.wb_primary_barcode?.toLowerCase().includes(needle) ?? false) ||
    row.wb_barcodes.some((b) => b.toLowerCase().includes(needle))
  )
}

function humanFfCatalogError(message: string): string {
  const normalized = message.trim()
  const lower = normalized.toLowerCase()
  if (
    lower === 'forbidden' ||
    lower.includes('forbidden') ||
    lower === 'seller_not_linked' ||
    normalized.includes('Нет доступа')
  ) {
    return 'Нет доступа к каталогу.'
  }
  if (
    lower === 'not_authenticated' ||
    lower === 'invalid_token' ||
    lower === 'user_not_found'
  ) {
    return 'Войдите заново.'
  }
  if (/^[a-z0-9_:-]+$/.test(normalized)) {
    return 'Не удалось загрузить каталог.'
  }
  return normalized || 'Не удалось загрузить каталог.'
}

export function FfProductsCatalogScreen({
  token,
  authHeaders,
  sellers,
  onSellersChanged,
  canManageCatalog = false,
}: Props) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSellerId, setSelectedSellerId] = useState<string>('__all__')
  const [searchQuery, setSearchQuery] = useState('')
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [editProduct, setEditProduct] = useState<FfCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [sellerCreateOpen, setSellerCreateOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      const sellerFilter = canManageCatalog && selectedSellerId !== '__all__' ? selectedSellerId : null
      const qs = sellerFilter ? `?seller_id=${encodeURIComponent(sellerFilter)}` : ''
      const res = await fetch(apiUrl(`/products/ff-catalog${qs}`), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      setCatalog((await res.json()) as FfCatalogRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
    } finally {
      setBusy(false)
    }
  }, [authHeaders, canManageCatalog, selectedSellerId, token])

  useEffect(() => {
    void load()
  }, [load])

  const rows = useMemo(() => {
    if (!canManageCatalog || selectedSellerId === '__all__') {
      return catalog
    }
    return catalog.filter((r) => r.seller_id === selectedSellerId)
  }, [canManageCatalog, catalog, selectedSellerId])

  const filteredRows = useMemo(
    () => rows.filter((r) => rowMatchesSearch(r, searchQuery)),
    [rows, searchQuery],
  )

  const sortedRows = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filteredRows].sort((a, b) => {
      const byName = a.name.localeCompare(b.name) * dir
      if (byName !== 0) return byName
      return a.sku_code.localeCompare(b.sku_code) * dir
    })
  }, [filteredRows, sortDir])

  function openPackagingEdit(p: FfCatalogRow) {
    setEditProduct(p)
    setEditText(p.packaging_instructions ?? '')
    setEditRequiresHonestSign(Boolean(p.requires_honest_sign))
  }

  function printPackagingTz() {
    if (!editProduct) return
    printPackagingInstructions({
      sku_code: editProduct.sku_code,
      product_name: editProduct.name,
      seller_name: editProduct.seller_name,
      instructions: editText,
      requires_honest_sign: editRequiresHonestSign,
    })
  }

  async function savePackagingInstructions() {
    if (!editProduct) return
    setEditBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/products/${editProduct.id}/packaging-instructions`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          packaging_instructions: editText.trim() || null,
          requires_honest_sign: editRequiresHonestSign,
        }),
      })
      if (!res.ok) {
        setError(humanFfCatalogError(await readApiErrorMessage(res)))
        return
      }
      setEditProduct(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить ТЗ.')
    } finally {
      setEditBusy(false)
    }
  }

  return (
    <FfProductMarkingPrintProvider token={token}>
      <Box
        sx={{
          minWidth: 0,
          width: '100%',
          maxWidth: 'calc(100vw - 308px)',
          boxSizing: 'border-box',
          overflowX: 'hidden',
        }}
      >
        <Typography variant="h5" gutterBottom>
          Каталог
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Карточки товаров селлеров: название, артикулы, ШК, размер и ТЗ упаковки.
        </Typography>

        {error ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-products-error">
            {error}
          </Alert>
        ) : null}
        {importNotice ? (
          <Alert
            severity="success"
            sx={{ mb: 2 }}
            data-testid="ff-products-import-notice"
            onClose={() => setImportNotice(null)}
          >
            {importNotice}
          </Alert>
        ) : null}

        <Paper
          variant="outlined"
          sx={{ p: 2, mb: 2, maxWidth: '100%', overflowX: 'hidden' }}
          data-testid="ff-products-filters"
        >
          <Stack spacing={2}>
            {canManageCatalog ? (
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                sx={{ justifyContent: 'flex-end' }}
              >
                <Button
                  variant="outlined"
                  onClick={() => setSellerCreateOpen(true)}
                  data-testid="ff-products-create-seller"
                >
                  Создать селлера
                </Button>
                <Button
                  variant="contained"
                  startIcon={<DownloadOutlinedIcon />}
                  onClick={() => setImportOpen(true)}
                  data-testid="ff-products-import-tz"
                >
                  Загрузить Excel
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => setCreateOpen(true)}
                  data-testid="ff-products-create"
                >
                  Создать товар
                </Button>
              </Stack>
            ) : null}
            <TextField
              fullWidth
              size="small"
              label="Поиск"
              placeholder="Название, артикул, SKU, ШК, WB/nmId или размер"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-products-search' } }}
            />
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2}
              sx={{ alignItems: { sm: 'center' } }}
            >
              {canManageCatalog ? (
                <FormControl size="small" sx={{ minWidth: 260 }}>
                  <InputLabel id="ff-products-seller-label">Селлер</InputLabel>
                  <Select
                    labelId="ff-products-seller-label"
                    label="Селлер"
                    value={selectedSellerId}
                    onChange={(e) => setSelectedSellerId(String(e.target.value))}
                    data-testid="ff-products-seller-filter"
                  >
                    <MenuItem value="__all__">Все</MenuItem>
                    {sellers.map((s) => (
                      <MenuItem key={s.id} value={s.id}>
                        {s.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              ) : null}
              {busy ? <CircularProgress size={18} data-testid="ff-products-loading" /> : null}
            </Stack>
          </Stack>
        </Paper>

        <TableContainer
          component={Paper}
          variant="outlined"
          sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'hidden' }}
          data-testid="ff-products-list"
        >
          <Table
            stickyHeader
            size="small"
            data-testid="ff-products-table"
            sx={{
              width: '100%',
              tableLayout: 'fixed',
              '& .MuiTableCell-root': {
                px: 1,
                py: 1,
                overflow: 'hidden',
                verticalAlign: 'middle',
              },
              '& .MuiTableCell-head': {
                fontWeight: 600,
                lineHeight: 1.2,
                whiteSpace: 'normal',
              },
            }}
          >
            <colgroup>
              <col style={{ width: '6%' }} />
              <col style={{ width: '20%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '9%' }} />
              <col style={{ width: '7%' }} />
              <col style={{ width: '11%' }} />
              <col style={{ width: '6%' }} />
              <col style={{ width: '4%' }} />
            </colgroup>
            <TableHead>
              <TableRow>
                <TableCell>Фото</TableCell>
                <TableCell>
                  <TableSortLabel
                    active
                    direction={sortDir}
                    onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
                    data-testid="ff-products-sort-name"
                  >
                    Название
                  </TableSortLabel>
                </TableCell>
                <TableCell>Артикул селлера</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>ШК</TableCell>
                <TableCell>WB/nmId</TableCell>
                <TableCell>Размер</TableCell>
                <TableCell>Селлер</TableCell>
                <TableCell>ТЗ</TableCell>
                <TableCell align="center" />
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedRows.map((p) => {
                const displayMeta = catalogRowToDisplayMeta(p)
                const barcode = resolveProductPrimaryBarcode(displayMeta)
                const markingCount = p.marking_available_count ?? 0
                return (
                  <TableRow key={p.id} hover data-testid="ff-product-row">
                    <TableCell>
                      <ProductPhotoThumb src={p.wb_primary_image_url} />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', minWidth: 0 }}>
                        <Typography
                          component="span"
                          variant="body2"
                          sx={{
                            minWidth: 0,
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {p.name}
                        </Typography>
                        {p.is_manual ? (
                          <Chip
                            size="small"
                            label="Вручную"
                            variant="outlined"
                            data-testid={`ff-product-manual-${p.id}`}
                          />
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.wb_vendor_code ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                        {p.sku_code}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box
                        sx={{
                          minWidth: 0,
                          maxWidth: '100%',
                          '& [data-testid^="ff-catalog-barcode-"]': { maxWidth: '100%' },
                        }}
                      >
                        <ProductBarcodeCell
                          barcode={barcode || null}
                          wb_size={null}
                          wb_composition={null}
                          testId={`ff-catalog-barcode-${p.id}`}
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.wb_nm_id ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.wb_size ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.seller_name ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0.5} sx={{ minWidth: 0, alignItems: 'flex-start' }}>
                        <Typography
                          variant="body2"
                          color={p.has_packaging_instructions ? 'text.primary' : 'text.secondary'}
                          data-testid={`ff-packaging-status-${p.id}`}
                          noWrap
                        >
                          {p.has_packaging_instructions ? 'Заполнено' : 'Нет ТЗ'}
                        </Typography>
                        {canManageCatalog ? (
                          <Button
                            size="small"
                            onClick={() => openPackagingEdit(p)}
                            data-testid={`ff-packaging-edit-${p.id}`}
                            sx={{ maxWidth: '100%', minWidth: 0, px: 0 }}
                          >
                            ТЗ
                          </Button>
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell align="center">
                      <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'center' }}>
                        <Tooltip
                          title={
                            canManageCatalog
                              ? `Коды маркировки: ${markingCount}`
                              : `Коды маркировки: ${markingCount}`
                          }
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label={`Коды маркировки ${p.sku_code}: ${markingCount}`}
                              data-testid={`ff-catalog-marking-link-${p.id}`}
                              disabled={!canManageCatalog}
                              onClick={() => navigate(`/app/ff/honest-sign/product/${p.id}`)}
                            >
                              <Badge
                                badgeContent={markingCount}
                                color="warning"
                                invisible={markingCount <= 0}
                                overlap="circular"
                              >
                                <QrCode2OutlinedIcon
                                  fontSize="small"
                                  color={markingCount > 0 ? 'warning' : 'disabled'}
                                />
                              </Badge>
                            </IconButton>
                          </span>
                        </Tooltip>
                        <ProductBarcodePrintButton
                          meta={displayMeta}
                          testId={`ff-catalog-print-${p.id}`}
                          productId={p.id}
                          requiresHonestSign={p.requires_honest_sign}
                          markingAvailable={markingCount}
                        />
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
              {sortedRows.length === 0 && !busy ? (
                <TableRow>
                  <TableCell colSpan={10}>
                    {searchQuery.trim() ? (
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        data-testid="ff-products-search-empty"
                      >
                        Ничего не найдено по запросу «{searchQuery.trim()}».
                      </Typography>
                    ) : canManageCatalog ? (
                      <Typography variant="body2" color="text.secondary" data-testid="ff-products-empty">
                        В каталоге пока нет товаров. Скачайте шаблон, загрузите Excel или создайте
                        один товар вручную.
                      </Typography>
                    ) : (
                      <Typography variant="body2" color="text.secondary" data-testid="ff-products-empty">
                        В каталоге пока нет товаров.
                      </Typography>
                    )}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>

        {canManageCatalog ? (
          <>
            <FfManualProductCreateDialog
              open={createOpen}
              token={token}
              authHeaders={authHeaders}
              sellers={sellers}
              defaultSellerId={selectedSellerId !== '__all__' ? selectedSellerId : null}
              onClose={() => setCreateOpen(false)}
              onCreated={async () => {
                setImportNotice('Товар создан.')
                await load()
              }}
            />
            <FfProductTzImportDialog
              open={importOpen}
              token={token}
              sellers={sellers}
              defaultSellerId={selectedSellerId !== '__all__' ? selectedSellerId : null}
              onClose={() => setImportOpen(false)}
              onApplied={async (message) => {
                setImportNotice(message)
                await load()
              }}
            />
            <FfSellerCreateDialog
              open={sellerCreateOpen}
              token={token}
              authHeaders={authHeaders}
              onClose={() => setSellerCreateOpen(false)}
              onCreated={async (created) => {
                await onSellersChanged?.()
                setSelectedSellerId(created.id)
                setImportNotice(`Селлер «${created.name}» создан и доступен для создания товаров.`)
              }}
            />
          </>
        ) : null}

        <Dialog
          open={editProduct !== null}
          onClose={() => setEditProduct(null)}
          fullWidth
          maxWidth="sm"
          data-testid="ff-packaging-dialog"
        >
          <DialogTitle>ТЗ на упаковку</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {editProduct?.sku_code} · {editProduct?.name}
            </Typography>
            <FormControlLabel
              control={
                <Checkbox
                  checked={editRequiresHonestSign}
                  onChange={(e) => setEditRequiresHonestSign(e.target.checked)}
                  data-testid="ff-requires-honest-sign"
                />
              }
              label="Нужен Честный знак при упаковке"
            />
            <TextField
              fullWidth
              multiline
              minRows={4}
              label="Инструкция для склада"
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'ff-packaging-text' } }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditProduct(null)} disabled={editBusy}>
              Отмена
            </Button>
            <Button
              variant="outlined"
              disabled={editBusy || !editProduct}
              onClick={printPackagingTz}
              data-testid="ff-packaging-print"
            >
              Печать
            </Button>
            <Button
              variant="contained"
              disabled={editBusy}
              onClick={() => void savePackagingInstructions()}
              data-testid="ff-packaging-save"
            >
              Сохранить
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    </FfProductMarkingPrintProvider>
  )
}
