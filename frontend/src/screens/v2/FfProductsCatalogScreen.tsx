import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Badge,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import QrCode2OutlinedIcon from '@mui/icons-material/QrCode2Outlined'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
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
  fbs_stock_sync_enabled?: boolean
  fbs_stock_limit?: number | null
  fbs_published_amount?: number | null
  fbs_sync_status?: string | null
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
  canManageCatalog?: boolean
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
  canManageCatalog = false,
}: Props) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  // Ширины колонок ужаты так, чтобы таблица (954px) целиком помещалась в контейнер на
  // 1280 (~970px) — тогда липкой колонке действий физически некуда сдвигаться, и она
  // не перекрывает соседей вовсе (тот же приём, что и в SellerInboundDraftScreen).
  // WB/nmId — служебный номенклатурный номер, который не ищут глазами, — сдвинут в
  // конец списка колонок, к липкой границе, а не «Название» или артикулы.
  const tableMinWidth = 954
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [dialogSellers, setDialogSellers] = useState<SellerRow[]>(sellers)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<string | null>(null)
  const [fbsLimitProduct, setFbsLimitProduct] = useState<FfCatalogRow | null>(null)
  const [fbsLimitDraft, setFbsLimitDraft] = useState('')
  const [fbsLimitSaving, setFbsLimitSaving] = useState(false)
  const [fbsLimitError, setFbsLimitError] = useState<string | null>(null)
  const fbsLimitAutoOpenedRef = useRef<string | null>(null)
  const [editProduct, setEditProduct] = useState<FfCatalogRow | null>(null)
  const [editText, setEditText] = useState('')
  const [editRequiresHonestSign, setEditRequiresHonestSign] = useState(false)
  const [editBusy, setEditBusy] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/products/ff-catalog'), {
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
  }, [authHeaders, token])

  useEffect(() => {
    void load()
  }, [load])

  const openFbsLimitDialog = useCallback((product: FfCatalogRow) => {
    setFbsLimitProduct(product)
    setFbsLimitDraft(product.fbs_stock_limit != null ? String(product.fbs_stock_limit) : '')
    setFbsLimitError(null)
  }, [])

  const closeFbsLimitDialog = useCallback(() => {
    if (fbsLimitSaving) return
    setFbsLimitProduct(null)
    setFbsLimitError(null)
  }, [fbsLimitSaving])

  const saveFbsLimit = useCallback(async () => {
    if (!fbsLimitProduct) return
    const trimmed = fbsLimitDraft.trim()
    let limitValue: number | null = null
    if (trimmed) {
      const parsed = Number(trimmed)
      if (!Number.isInteger(parsed) || parsed < 0) {
        setFbsLimitError('Введите целое число не меньше 0 или оставьте поле пустым.')
        return
      }
      limitValue = parsed
    }
    setFbsLimitSaving(true)
    setFbsLimitError(null)
    try {
      const res = await fetch(apiUrl(`/products/${fbsLimitProduct.id}/fbs-stock-sync`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ fbs_stock_limit: limitValue }),
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      setImportNotice(
        limitValue != null
          ? `Остаток FBS для «${fbsLimitProduct.sku_code}» обновлён: ${limitValue} шт.`
          : `Остаток FBS для «${fbsLimitProduct.sku_code}» сброшен.`,
      )
      setFbsLimitProduct(null)
      await load()
    } catch (e) {
      setFbsLimitError(e instanceof Error ? e.message : 'Не удалось сохранить остаток FBS.')
    } finally {
      setFbsLimitSaving(false)
    }
  }, [authHeaders, fbsLimitDraft, fbsLimitProduct, load, token])

  useEffect(() => {
    const targetId = searchParams.get('fbs_limit')
    if (!targetId || catalog.length === 0) return
    if (fbsLimitAutoOpenedRef.current === targetId) return
    const match = catalog.find((p) => p.id === targetId)
    if (match) {
      openFbsLimitDialog(match)
    }
    fbsLimitAutoOpenedRef.current = targetId
    const next = new URLSearchParams(searchParams)
    next.delete('fbs_limit')
    setSearchParams(next, { replace: true })
  }, [catalog, openFbsLimitDialog, searchParams, setSearchParams])

  useEffect(() => {
    if (sellers.length > 0) {
      setDialogSellers(sellers)
    }
  }, [sellers])

  const loadDialogSellers = useCallback(async (): Promise<SellerRow[]> => {
    if (!canManageCatalog) return []
    try {
      const res = await fetch(apiUrl('/sellers'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        throw new Error(humanFfCatalogError(await readApiErrorMessage(res)))
      }
      const rows = (await res.json()) as SellerRow[]
      setDialogSellers(rows)
      return rows
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить селлеров.')
      return []
    }
  }, [authHeaders, canManageCatalog, token])

  useEffect(() => {
    void loadDialogSellers()
  }, [loadDialogSellers])

  const openCreateDialog = useCallback(async () => {
    await loadDialogSellers()
    setCreateOpen(true)
  }, [loadDialogSellers])

  const openImportDialog = useCallback(async () => {
    await loadDialogSellers()
    setImportOpen(true)
  }, [loadDialogSellers])

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

        {/* GLOBAL-02: две кнопки не нуждаются в отдельной карточке во всю ширину —
            рамка вокруг пустоты только раздувает экран. Действия идут прямо над таблицей. */}
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          sx={{ mb: 2, maxWidth: '100%', justifyContent: 'flex-end', alignItems: { sm: 'center' } }}
          data-testid="ff-products-actions"
        >
          {busy ? <CircularProgress size={18} data-testid="ff-products-loading" /> : null}
          {canManageCatalog ? (
            <>
              <Button
                variant="contained"
                startIcon={<DownloadOutlinedIcon />}
                onClick={() => void openImportDialog()}
                data-testid="ff-products-import-tz"
              >
                Загрузить Excel
              </Button>
              <Button
                variant="outlined"
                onClick={() => void openCreateDialog()}
                data-testid="ff-products-create"
              >
                Создать товар
              </Button>
            </>
          ) : null}
        </Stack>

        <TableContainer
          component={Paper}
          variant="outlined"
          sx={{ width: '100%', maxWidth: '100%', minWidth: 0, overflowX: 'auto' }}
          data-testid="ff-products-list"
        >
          <Table
            stickyHeader
            size="small"
            data-testid="ff-products-table"
            sx={{
              minWidth: tableMinWidth,
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
              <col style={{ width: 56 }} />
              <col style={{ width: 140 }} />
              <col style={{ width: 119 }} />
              <col style={{ width: 118 }} />
              <col style={{ width: 112 }} />
              <col style={{ width: 64 }} />
              <col style={{ width: 75 }} />
              <col style={{ width: 96 }} />
              <col style={{ width: 78 }} />
              <col style={{ width: 96 }} />
            </colgroup>
            <TableHead>
              <TableRow>
                <TableCell>Фото</TableCell>
                <TableCell>Название</TableCell>
                <TableCell>Артикул селлера</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>ШК</TableCell>
                <TableCell>Размер</TableCell>
                <TableCell>Селлер</TableCell>
                <TableCell>ТЗ</TableCell>
                <TableCell>WB/nmId</TableCell>
                <TableCell
                  align="center"
                  sx={{
                    position: 'sticky',
                    right: 0,
                    zIndex: 3,
                    bgcolor: 'background.paper',
                    borderLeft: '1px solid',
                    borderLeftColor: 'divider',
                  }}
                />
              </TableRow>
            </TableHead>
            <TableBody>
              {catalog.map((p) => {
                const displayMeta = catalogRowToDisplayMeta(p)
                const barcode = resolveProductPrimaryBarcode(displayMeta)
                const markingCount = p.marking_available_count ?? 0
                return (
                  <TableRow key={p.id} hover data-testid="ff-product-row">
                    <TableCell>
                      <ProductPhotoThumb src={p.wb_primary_image_url} />
                    </TableCell>
                    <TableCell>
                      <Typography
                        component="span"
                        variant="body2"
                        title={p.name}
                        sx={{
                          minWidth: 0,
                          display: '-webkit-box',
                          WebkitBoxOrient: 'vertical',
                          WebkitLineClamp: 2,
                          overflow: 'hidden',
                          lineHeight: 1.25,
                        }}
                      >
                        {p.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                        {p.wb_vendor_code ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
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
                        {p.wb_size ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{ wordBreak: 'break-word' }}
                      >
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
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.wb_nm_id ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell
                      align="center"
                      sx={{
                        position: 'sticky',
                        right: 0,
                        zIndex: 1,
                        bgcolor: 'background.paper',
                        borderLeft: '1px solid',
                        borderLeftColor: 'divider',
                      }}
                    >
                      <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'center' }}>
                        <Tooltip
                          title={`Коды маркировки: ${markingCount}`}
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
                        <Tooltip
                          title={
                            p.fbs_stock_limit != null
                              ? `Остаток FBS: ${p.fbs_stock_limit} шт`
                              : 'Остаток FBS не задан'
                          }
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label={`Остаток FBS ${p.sku_code}`}
                              data-testid={`ff-catalog-fbs-limit-${p.id}`}
                              disabled={!canManageCatalog}
                              onClick={() => openFbsLimitDialog(p)}
                            >
                              <Inventory2OutlinedIcon
                                fontSize="small"
                                color={p.fbs_stock_limit != null ? 'primary' : 'disabled'}
                              />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
              {catalog.length === 0 && !busy ? (
                <TableRow>
                  <TableCell colSpan={10}>
                    {canManageCatalog ? (
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
              sellers={dialogSellers}
              onClose={() => setCreateOpen(false)}
              onCreated={async () => {
                setImportNotice('Товар создан.')
                await load()
              }}
            />
            <FfProductTzImportDialog
              open={importOpen}
              token={token}
              sellers={dialogSellers}
              onClose={() => setImportOpen(false)}
              onApplied={async (message) => {
                setImportNotice(message)
                await load()
              }}
            />
          </>
        ) : null}

        <Dialog
          open={fbsLimitProduct != null}
          onClose={closeFbsLimitDialog}
          maxWidth="xs"
          fullWidth
          data-testid="ff-catalog-fbs-limit-dialog"
        >
          <DialogTitle>Остаток FBS</DialogTitle>
          <DialogContent>
            {fbsLimitProduct ? (
              <Stack spacing={2} sx={{ pt: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  {fbsLimitProduct.sku_code} · {fbsLimitProduct.name}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Максимальное количество этого товара, доступное для продажи по FBS. От
                  этого числа делится остаток по складам WB на экране «Остатки WB».
                </Typography>
                {fbsLimitError ? (
                  <Alert severity="error" data-testid="ff-catalog-fbs-limit-error">
                    {fbsLimitError}
                  </Alert>
                ) : null}
                <TextField
                  label="Остаток FBS (шт)"
                  type="number"
                  value={fbsLimitDraft}
                  onChange={(e) => setFbsLimitDraft(e.target.value)}
                  placeholder="Не задан"
                  slotProps={{ htmlInput: { min: 0, 'data-testid': 'ff-catalog-fbs-limit-input' } }}
                  fullWidth
                  disabled={fbsLimitSaving}
                />
              </Stack>
            ) : null}
          </DialogContent>
          <DialogActions>
            <Button onClick={closeFbsLimitDialog} disabled={fbsLimitSaving}>
              Отмена
            </Button>
            <Button
              variant="contained"
              onClick={() => void saveFbsLimit()}
              disabled={fbsLimitSaving}
              data-testid="ff-catalog-fbs-limit-save"
            >
              {fbsLimitSaving ? 'Сохраняем…' : 'Сохранить'}
            </Button>
          </DialogActions>
        </Dialog>

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
