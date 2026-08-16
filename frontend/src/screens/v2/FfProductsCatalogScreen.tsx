import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Badge,
  Box,
  Button,
  CircularProgress,
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
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import QrCode2OutlinedIcon from '@mui/icons-material/QrCode2Outlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { ProductBarcodeCell } from '../../components/ProductBarcodeCell'
import { ProductBarcodePrintButton } from '../../components/ProductBarcodePrintButton'
import { FfProductMarkingPrintProvider } from '../../components/FfProductMarkingPrintProvider'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<FfCatalogRow[]>([])
  const [dialogSellers, setDialogSellers] = useState<SellerRow[]>(sellers)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<string | null>(null)

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
              minWidth: 1180,
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
              <col style={{ width: 240 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 150 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 76 }} />
              <col style={{ width: 140 }} />
              <col style={{ width: 92 }} />
              <col style={{ width: 96 }} />
            </colgroup>
            <TableHead>
              <TableRow>
                <TableCell>Фото</TableCell>
                <TableCell>Название</TableCell>
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
                      </Stack>
                    </TableCell>
                    <TableCell align="center">
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
      </Box>
    </FfProductMarkingPrintProvider>
  )
}
