import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import {
  Alert,
  Box,
  Button,
  Chip,
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
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { WmsDateField } from '../../components/WmsDateField'
import { SellerWbProductPickerDialog } from '../../components/SellerWbProductPickerDialog'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { ProductBarcodeCell } from '../../components/ProductBarcodeCell'
import { ProductBarcodePrintDialog } from '../../components/ProductBarcodePrintDialog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { formatHumanDocumentNumber } from '../ff/documentDisplay'
import {
  inboundOperationTypeLabel,
  normalizeInboundOperationType,
  type InboundOperationType,
} from '../../utils/inboundOperationType'
import type { ProductLineDisplayMeta } from '../../types/wbProductCatalog'

export type WbCatalogRow = {
  id: string
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size?: string | null
  wb_composition?: string | null
}

type InboundLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  wb_barcode: string | null
  requires_honest_sign: boolean
  added_by_fulfillment: boolean
  expected_qty: number
  actual_qty: number | null
  effective_actual_qty: number | null
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type InboundBox = {
  id: string
}

type InboundDetail = {
  id: string
  waybill_number: string | null
  display_number?: string | null
  document_number?: string | null
  warehouse_id: string
  warehouse_name?: string | null
  status: string
  operation_type: InboundOperationType
  planned_delivery_date: string | null
  planned_box_count: number | null
  actual_box_count: number | null
  boxes_discrepancy: boolean
  has_discrepancy: boolean
  boxes?: InboundBox[]
  lines: InboundLine[]
}

type WarehouseRow = { id: string; name: string; code: string }
const UNKNOWN_INBOUND_STATUS_LABEL = 'Статус уточняется'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  warehouseId: string | null
  warehouses?: WarehouseRow[]
  onRefreshInboundList: () => void | Promise<void>
}

export function sellerInboundStatusRu(status: string): string {
  if (status === 'draft') {
    return 'Черновик'
  }
  if (status === 'submitted') {
    return 'Передано на склад'
  }
  if (status === 'receiving') {
    return 'Принимается на складе'
  }
  if (status === 'sorting') {
    return 'В сортировке'
  }
  if (status === 'done') {
    return 'Проведено'
  }
  if (status === 'primary_accepted') {
    return 'Принято на складе'
  }
  if (status === 'verifying') {
    return 'Проверка на складе'
  }
  if (status === 'verified') {
    return 'Проверено на складе'
  }
  if (status === 'posted') {
    return 'Оприходовано'
  }
  return UNKNOWN_INBOUND_STATUS_LABEL
}

function operationTypeRu(operationType: unknown): string {
  return inboundOperationTypeLabel(operationType)
}

function lineActualQty(line: InboundLine): number {
  return line.effective_actual_qty ?? line.actual_qty ?? 0
}

function discrepancyText(delta: number): string {
  if (delta === 0) {
    return 'ОК'
  }
  if (delta > 0) {
    return `Излишек ${delta}`
  }
  return `Недостача ${Math.abs(delta)}`
}

function lineHasFactData(line: InboundLine): boolean {
  return (
    line.actual_qty != null ||
    line.effective_actual_qty != null ||
    line.added_by_fulfillment ||
    line.posted_qty > 0
  )
}

export function shouldShowSellerInboundNoWarehouse(
  warehouseId: string | null,
  routeRequestId: string | null,
  detailStatus: string | null,
): boolean {
  return !warehouseId && (!routeRequestId || detailStatus === 'draft')
}

export function shouldShowSellerInboundLoadError(
  hasDetail: boolean,
  localError: string | null,
): boolean {
  return !hasDetail && localError !== null
}

export function sellerInboundPendingText(routeRequestId: string | null): string {
  return routeRequestId ? 'Загружаем карточку приёмки…' : 'Создаём черновик…'
}

export function SellerInboundDraftScreen({
  token,
  authHeaders,
  warehouseId,
  warehouses = [],
  onRefreshInboundList,
}: Props) {
  const navigate = useNavigate()
  const navigateToDocuments = useCallback(() => {
    navigate('../documents')
  }, [navigate])
  const params = useParams()
  const [searchParams] = useSearchParams()
  const routeRequestId = (params as { requestId?: string }).requestId ?? null
  const requestedOperationType = useMemo(
    () => normalizeInboundOperationType(searchParams.get('operation')),
    [searchParams],
  )
  const createOnceRef = useRef<Promise<string> | null>(null)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [detail, setDetail] = useState<InboundDetail | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[] | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [printMeta, setPrintMeta] = useState<ProductLineDisplayMeta | null>(null)
  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')
  const [plannedBoxCountDraft, setPlannedBoxCountDraft] = useState<string>('')
  const [localNotice, setLocalNotice] = useState<string | null>(null)

  const loadDetail = useCallback(
    async (rid: string) => {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${rid}`), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      setDetail((await res.json()) as InboundDetail)
    },
    [authHeaders, token],
  )

  useEffect(() => {
    if (!token) {
      return
    }
    if (routeRequestId) {
      setRequestId(routeRequestId)
      void loadDetail(routeRequestId)
      return
    }
    if (!warehouseId) {
      return
    }
    if (!createOnceRef.current) {
      createOnceRef.current = (async () => {
        const today = new Date().toISOString().slice(0, 10)
        const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            warehouse_id: warehouseId,
            planned_delivery_date: today,
            operation_type: requestedOperationType,
          }),
        })
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        const j = (await res.json()) as { id: string }
        return j.id
      })()
    }
    let cancelled = false
    void (async () => {
      try {
        const id = await createOnceRef.current
        if (cancelled || !id) {
          return
        }
        setRequestId(id)
        await loadDetail(id)
      } catch (e) {
        if (!cancelled) {
          setLocalError(
            e instanceof Error
              ? e.message
              : requestedOperationType === 'return'
                ? 'Не удалось создать возврат. Проверьте склад и попробуйте ещё раз.'
                : 'Не удалось создать заявку.',
          )
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, loadDetail, requestedOperationType, routeRequestId, token, warehouseId])

  useEffect(() => {
    setPlannedDateDraft(detail?.planned_delivery_date ?? '')
  }, [detail?.planned_delivery_date])

  useEffect(() => {
    if (detail?.planned_box_count != null) {
      setPlannedBoxCountDraft(String(detail.planned_box_count))
    } else {
      setPlannedBoxCountDraft('')
    }
  }, [detail?.planned_box_count])

  const catalogById = useMemo(() => {
    const m = new Map<string, WbCatalogRow>()
    if (catalog) {
      for (const r of catalog) {
        m.set(r.id, r)
      }
    }
    return m
  }, [catalog])

  const lineProductIds = useMemo(() => new Set(detail?.lines.map((l) => l.product_id) ?? []), [detail])

  useEffect(() => {
    if (!token) {
      return
    }
    if (catalog !== null) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(apiUrl('/products/wb-catalog'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          return
        }
        const rows = (await res.json()) as WbCatalogRow[]
        if (!cancelled) {
          setCatalog(rows)
        }
      } catch {
        // silent: photos are optional; picker will show explicit error if user opens it
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, catalog, token])

  const openPicker = async () => {
    setLocalError(null)
    if (catalog === null) {
      try {
        const res = await fetch(apiUrl('/products/wb-catalog'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          setLocalError(await readApiErrorMessage(res))
          return
        }
        setCatalog((await res.json()) as WbCatalogRow[])
      } catch (e) {
        setLocalError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
        return
      }
    }
    setPickerOpen(true)
  }

  const applyPicker = async (pickerQtyByProduct: Record<string, number>) => {
    if (!requestId || !detail) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const lineByProduct = new Map(detail.lines.map((ln) => [ln.product_id, ln]))
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) {
          continue
        }
        const existing = lineByProduct.get(productId)
        if (existing) {
          const next = existing.expected_qty + addQty
          const res = await fetch(
            apiUrl(
              `/operations/inbound-intake-requests/${requestId}/lines/${existing.id}/expected`,
            ),
            {
              method: 'PATCH',
              headers: {
                ...authHeaders(token),
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ expected_qty: next }),
            },
          )
          if (!res.ok) {
            setLocalError(await readApiErrorMessage(res))
            setBusy(false)
            return
          }
        } else {
          const res = await fetch(
            apiUrl(`/operations/inbound-intake-requests/${requestId}/lines`),
            {
              method: 'POST',
              headers: {
                ...authHeaders(token),
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ product_id: productId, expected_qty: addQty }),
            },
          )
          if (!res.ok) {
            setLocalError(await readApiErrorMessage(res))
            setBusy(false)
            return
          }
        }
      }
      setPickerOpen(false)
      await loadDetail(requestId)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      setBusy(false)
    }
  }

  const patchDraftField = async (body: Record<string, unknown>): Promise<boolean> => {
    if (!requestId) {
      return false
    }
    setBusy(true)
    setLocalError(null)
    setLocalNotice(null)
    try {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return false
      }
      setDetail((await res.json()) as InboundDetail)
      return true
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось сохранить заявку.')
      return false
    } finally {
      setBusy(false)
    }
  }

  const parsedPlannedBoxCount = (): number | null => {
    const raw = plannedBoxCountDraft.trim()
    if (!raw) {
      return null
    }
    const n = Math.floor(Number(raw))
    return Number.isFinite(n) && n >= 1 ? n : null
  }

  const displayDocumentNumber = useMemo(() => formatHumanDocumentNumber(detail), [detail])

  const draftFieldsDirty = useMemo(() => {
    if (!detail) {
      return false
    }
    const detailDate = detail.planned_delivery_date ?? ''
    const draftBox = parsedPlannedBoxCount()
    const detailBox = detail.planned_box_count ?? null
    return (
      plannedDateDraft !== detailDate ||
      draftBox !== detailBox
    )
  }, [detail, plannedBoxCountDraft, plannedDateDraft])

  const saveDraftFields = async (): Promise<boolean> => {
    const plannedBoxCount = parsedPlannedBoxCount()
    const ok = await patchDraftField({
      planned_delivery_date: plannedDateDraft || null,
      planned_box_count: plannedBoxCount,
    })
    if (ok) {
      setLocalNotice('Заявка сохранена.')
      await onRefreshInboundList()
    }
    return ok
  }

  const patchLineQty = async (lineId: string, expectedQty: number) => {
    if (!requestId) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}/expected`),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ expected_qty: expectedQty }),
        },
      )
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail(requestId)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось сохранить количество.')
    } finally {
      setBusy(false)
    }
  }

  const deleteLine = async (lineId: string) => {
    if (!requestId) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}`),
        {
          method: 'DELETE',
          headers: { ...authHeaders(token) },
        },
      )
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail(requestId)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось удалить строку.')
    } finally {
      setBusy(false)
    }
  }

  const submitToWarehouse = async () => {
    if (!requestId) {
      return
    }
    const plannedBoxCount = parsedPlannedBoxCount()
    if (plannedBoxCount == null) {
      setLocalError('Укажите количество грузомест')
      return
    }
    if (!(await saveDraftFields())) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/submit`),
        {
          method: 'POST',
          headers: { ...authHeaders(token) },
        },
      )
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      await onRefreshInboundList()
      navigateToDocuments()
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось передать на склад.')
    } finally {
      setBusy(false)
    }
  }

  const closeDocument = () => {
    if (draftFieldsDirty && !window.confirm('Закрыть без сохранения?')) {
      return
    }
    navigateToDocuments()
  }

  const linePrintMeta = (line: InboundLine, cat: WbCatalogRow | undefined): ProductLineDisplayMeta => {
    const barcode =
      cat?.wb_primary_barcode ??
      line.wb_barcode ??
      (cat?.wb_barcodes.length ? cat.wb_barcodes[0] ?? null : null)
    return {
      sku_code: cat?.sku_code ?? line.sku_code,
      product_name: cat?.name ?? line.product_name,
      seller_name: null,
      wb_primary_image_url: cat?.wb_primary_image_url ?? null,
      wb_primary_barcode: barcode,
      wb_barcodes: cat?.wb_barcodes ?? (line.wb_barcode ? [line.wb_barcode] : []),
      wb_vendor_code: cat?.wb_vendor_code ?? null,
      wb_nm_id: cat?.wb_nm_id ?? null,
      wb_size: cat?.wb_size ?? null,
      wb_color: null,
      wb_brand: null,
      wb_composition: cat?.wb_composition ?? null,
      packaging_instructions: null,
    }
  }

  const hasWarehouseContext = Boolean(warehouseId) || warehouses.length > 0
  const sellerCanEdit =
    detail != null &&
    (detail.status === 'draft' ||
      (detail.status === 'submitted' && hasWarehouseContext))
  const draftLocked = detail != null && !sellerCanEdit
  const readOnlyHint =
    detail?.status === 'submitted' && !hasWarehouseContext
      ? 'Склад не загрузился, поэтому заявка открыта только для просмотра. Обновите страницу или вернитесь к документам.'
      : 'Приёмку взял в работу склад, изменения теперь вносит фулфилмент'
  const draftOperationLabel = operationTypeRu(detail?.operation_type ?? requestedOperationType)
  const newDraftTitle =
    draftOperationLabel === 'Возврат' ? 'Новая заявка на возврат' : 'Новая заявка на поставку'
  const pageTitle = detail
    ? sellerCanEdit
      ? detail.status === 'submitted'
        ? `Заявка передана на склад · ${operationTypeRu(detail.operation_type)}`
        : newDraftTitle
      : `Карточка приёмки · ${operationTypeRu(detail.operation_type)}`
    : routeRequestId
      ? 'Карточка приёмки'
      : newDraftTitle
  const warehouseLabel = useMemo(() => {
    if (!detail) {
      return '—'
    }
    const matched = warehouses.find((w) => w.id === detail.warehouse_id)
    if (matched) {
      return `${matched.name} (${matched.code})`
    }
    return 'Склад ФФ'
  }, [detail, warehouses])

  const showLoadError = routeRequestId
    ? shouldShowSellerInboundLoadError(detail !== null, localError)
    : false

  if (shouldShowSellerInboundNoWarehouse(warehouseId, routeRequestId, detail?.status ?? null)) {
    return (
      <Alert severity="warning" data-testid="seller-inbound-no-warehouse">
        Нет доступного склада для создания заявки. Обратитесь к фулфилменту.
      </Alert>
    )
  }

  return (
    <Box
      data-testid="seller-inbound-draft-root"
      sx={{
        width: 'calc(100vw - 288px)',
        maxWidth: '100%',
        minWidth: 0,
        overflowX: 'hidden',
      }}
    >
      <Typography variant="h5" gutterBottom>
        {pageTitle}
      </Typography>
      {localError && !showLoadError ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-inbound-draft-error">
          {localError}
        </Alert>
      ) : null}
      {localNotice ? (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="seller-inbound-draft-ok">
          {localNotice}
        </Alert>
      ) : null}
      {detail && !sellerCanEdit ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="seller-inbound-readonly-hint">
          {readOnlyHint}
        </Alert>
      ) : null}

      {!requestId || !detail ? (
        showLoadError ? (
          <Paper
            variant="outlined"
            sx={{ p: 2, minHeight: '24vh' }}
            data-testid="seller-inbound-draft-load-error"
          >
            <Stack spacing={1.5} sx={{ alignItems: 'flex-start' }}>
              <Typography variant="subtitle2">Не удалось открыть карточку приёмки</Typography>
              <Typography variant="body2" color="text.secondary">
                Повторите попытку или вернитесь к документам.
              </Typography>
              {routeRequestId ? (
                <Button variant="outlined" onClick={() => void loadDetail(routeRequestId)}>
                  Повторить
                </Button>
              ) : null}
              <Button variant="outlined" onClick={navigateToDocuments}>
                К документам
              </Button>
            </Stack>
          </Paper>
        ) : (
          <Stack sx={{ py: 4, alignItems: 'center' }}>
            <CircularProgress data-testid="seller-inbound-draft-loading" />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {sellerInboundPendingText(routeRequestId)}
            </Typography>
          </Stack>
        )
      ) : (
        <Paper
          variant="outlined"
          sx={{
            p: 2,
            minHeight: '38vh',
            minWidth: 0,
            maxWidth: '100%',
            overflow: 'hidden',
          }}
          data-testid="seller-inbound-draft-form"
        >
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            useFlexGap
            sx={{ mb: 2, alignItems: { md: 'center' }, flexWrap: 'wrap' }}
          >
            <WmsDateField
              label="Дата поставки (план)"
              value={plannedDateDraft || null}
              onChange={(iso) => {
                setPlannedDateDraft(iso ?? '')
              }}
              disabled={!sellerCanEdit || busy}
              required
              testId="seller-inbound-planned-date"
              slotProps={{ textField: { fullWidth: false, sx: { minWidth: 220 } } }}
            />
            <TextField
              label="Грузомест"
              type="number"
              size="small"
              disabled={!sellerCanEdit || busy}
              value={plannedBoxCountDraft}
              onChange={(e) => setPlannedBoxCountDraft(e.target.value)}
              sx={{ minWidth: 150 }}
              slotProps={{
                htmlInput: {
                  min: 0,
                  'data-testid': 'seller-inbound-planned-boxes',
                },
              }}
            />
            {displayDocumentNumber ? (
              <Typography
                variant="body2"
                color="text.secondary"
                data-testid="seller-inbound-document-number"
              >
                Номер: <strong>{displayDocumentNumber}</strong>
              </Typography>
            ) : null}
            <Chip
              label={sellerInboundStatusRu(detail.status)}
              color={detail.status === 'draft' ? 'default' : 'primary'}
              data-testid="seller-inbound-status-chip"
            />
            <Typography variant="body2" color="text.secondary" data-testid="seller-inbound-operation-type">
              Тип: <strong>{operationTypeRu(detail.operation_type)}</strong>
            </Typography>
            <Tooltip title={warehouseLabel}>
              <Typography
                variant="body2"
                color="text.secondary"
                noWrap
                data-testid="seller-inbound-warehouse-label"
                data-task-id="BL-2"
                sx={{ maxWidth: { xs: '100%', md: 260 }, minWidth: 0 }}
              >
                Склад: <strong>{warehouseLabel}</strong>
              </Typography>
            </Tooltip>
            <Box sx={{ flexGrow: 1 }} />
            {sellerCanEdit ? (
              <Button
                variant="outlined"
                disabled={busy}
                onClick={() => void openPicker()}
                data-testid="seller-inbound-add-products"
                sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                Добавить товары
              </Button>
            ) : null}
            {sellerCanEdit ? (
              <Button
                variant="outlined"
                disabled={busy}
                onClick={() => void saveDraftFields()}
                data-testid="seller-inbound-save-draft"
                sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                Сохранить
              </Button>
            ) : null}
            <Button
              variant="outlined"
              disabled={busy}
              onClick={closeDocument}
              data-testid="seller-inbound-close"
              sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
            >
              Закрыть
            </Button>
            {detail.status === 'draft' ? (
              <Button
                variant="contained"
                color="secondary"
                disabled={draftLocked || busy || detail.lines.length === 0}
                onClick={() => void submitToWarehouse()}
                data-testid="seller-inbound-submit-warehouse"
                sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                Передать на склад
              </Button>
            ) : null}
          </Stack>

          <TableContainer
            sx={{
              width: '100%',
              maxWidth: '100%',
              minWidth: 0,
              overflowX: 'auto',
              overflowY: 'hidden',
            }}
          >
            <Table
              size="small"
              data-testid="seller-inbound-lines-table"
              sx={{
                tableLayout: 'fixed',
                width: '100%',
                minWidth: 1096,
                '& th': { py: 1, lineHeight: 1.2, verticalAlign: 'bottom' },
                '& td': { py: 1.25, verticalAlign: 'top' },
              }}
            >
              <colgroup>
                <col style={{ width: 56 }} />
                <col style={{ width: 132 }} />
                <col style={{ width: 160 }} />
                <col style={{ width: 128 }} />
                <col style={{ width: 96 }} />
                <col style={{ width: 272 }} />
                <col style={{ width: 104 }} />
                <col style={{ width: 56 }} />
                <col style={{ width: 92 }} />
              </colgroup>
              <TableHead>
                <TableRow>
                  <TableCell>Фото</TableCell>
                  <TableCell sx={{ pl: 2 }}>Артикул</TableCell>
                  <TableCell>ШК</TableCell>
                  <TableCell>Артикул продавца</TableCell>
                  <TableCell sx={{ pr: 2 }}>Артикул WB</TableCell>
                  <TableCell sx={{ pl: 2 }}>Наименование</TableCell>
                  <TableCell align="right">
                    Кол-во
                  </TableCell>
                  <TableCell align="center">Печать</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {detail.lines.map((ln) => {
                  const cat = catalogById.get(ln.product_id)
                  const img = cat?.wb_primary_image_url ?? undefined
                  const barcode =
                    cat?.wb_primary_barcode ??
                    ln.wb_barcode ??
                    (cat?.wb_barcodes.length ? cat.wb_barcodes[0] ?? null : null)
                  const printLineMeta = linePrintMeta(ln, cat)
                  const factActual = lineActualQty(ln)
                  const factDelta = factActual - ln.expected_qty
                  const showFactCaption = draftLocked && lineHasFactData(ln)
                  return (
                    <TableRow
                      key={ln.id}
                      hover
                      data-testid="seller-inbound-line-row"
                      sx={{
                        '& td': {
                          px: 1.25,
                        },
                        '& td:first-of-type': { pl: 1 },
                        '& td:last-of-type': { pr: 1 },
                      }}
                    >
                      <TableCell>
                        <ProductPhotoThumb src={img} />
                      </TableCell>
                      <TableCell
                        sx={{
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          pl: 2,
                        }}
                        title={ln.sku_code}
                      >
                        {ln.sku_code}
                      </TableCell>
                      <TableCell sx={{ overflow: 'hidden' }}>
                        <Box
                          sx={{
                            maxWidth: '100%',
                            overflow: 'hidden',
                            '& > .MuiTypography-root': { maxWidth: '100%' },
                            '& > .MuiTypography-root > span:first-of-type': {
                              display: 'block',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            },
                          }}
                        >
                          <ProductBarcodeCell
                            barcode={barcode}
                            wb_size={cat?.wb_size}
                            wb_composition={cat?.wb_composition}
                          />
                        </Box>
                      </TableCell>
                      <TableCell
                        sx={{
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                        title={cat?.wb_vendor_code ?? '—'}
                      >
                        {cat?.wb_vendor_code ?? '—'}
                      </TableCell>
                      <TableCell
                        sx={{
                          overflow: 'hidden',
                          whiteSpace: 'nowrap',
                          textOverflow: 'ellipsis',
                          pr: 2,
                        }}
                        title={cat?.wb_nm_id ? String(cat.wb_nm_id) : undefined}
                      >
                        {cat?.wb_nm_id ?? '—'}
                      </TableCell>
                      <TableCell sx={{ pl: 2, overflow: 'hidden' }}>
                        <Typography
                          variant="body2"
                          title={ln.product_name}
                          sx={{
                            lineHeight: 1.25,
                            display: '-webkit-box',
                            overflow: 'hidden',
                            overflowWrap: 'break-word',
                            WebkitBoxOrient: 'vertical',
                            WebkitLineClamp: ln.added_by_fulfillment ? 2 : 3,
                          }}
                        >
                          {ln.product_name}
                        </Typography>
                        {ln.added_by_fulfillment ? (
                          <Typography
                            variant="caption"
                            color="error"
                            data-testid="seller-inbound-line-added-by-ff"
                            sx={{
                              display: 'block',
                              mt: 0.25,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Добавлено ФФ
                          </Typography>
                        ) : null}
                        {showFactCaption ? (
                          <Typography
                            variant="caption"
                            color={factDelta !== 0 ? 'error' : 'text.secondary'}
                            data-testid="seller-inbound-line-fact"
                            sx={{
                              display: 'block',
                              mt: 0.25,
                              fontWeight: factDelta !== 0 ? 700 : 400,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Принято: {factActual} · {discrepancyText(factDelta)}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                        <TextField
                          type="number"
                          size="small"
                          sx={{ width: 72 }}
                          disabled={!sellerCanEdit || busy}
                          defaultValue={ln.expected_qty}
                          key={`${ln.id}-${ln.expected_qty}`}
                          onBlur={(e) => {
                            const v = Number(e.target.value)
                            if (!Number.isFinite(v) || v < 1) {
                              return
                            }
                            if (v !== ln.expected_qty) {
                              void patchLineQty(ln.id, v)
                            }
                          }}
                          slotProps={{
                            htmlInput: { min: 1, 'data-testid': 'seller-inbound-line-qty' },
                          }}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Tooltip title="Печать товарного ШК">
                          <span>
                            <IconButton
                              size="small"
                              disabled={!printLineMeta.wb_primary_barcode}
                              onClick={() => setPrintMeta(printLineMeta)}
                              data-testid="seller-inbound-line-print-barcode"
                              aria-label="Печать товарного ШК"
                            >
                              <PrintOutlined fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        {sellerCanEdit ? (
                          <Button
                            size="small"
                            color="error"
                            disabled={busy}
                            onClick={() => void deleteLine(ln.id)}
                            data-testid="seller-inbound-line-delete"
                          >
                            Удалить
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  )
                })}
                {detail.lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9}>
                      <Typography variant="body2" color="text.secondary">
                        {sellerCanEdit
                          ? 'Добавьте товары кнопкой «Добавить товары».'
                          : 'В документе нет товаров.'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      <SellerWbProductPickerDialog
        open={pickerOpen}
        busy={busy}
        catalog={catalog}
        disabledProductIds={lineProductIds}
        testIdPrefix="seller-inbound-picker"
        qtyColumnLabel="Кол-во в заявку"
        onClose={() => setPickerOpen(false)}
        onApply={applyPicker}
      />
      <ProductBarcodePrintDialog
        open={printMeta !== null}
        meta={printMeta}
        onClose={() => setPrintMeta(null)}
      />
    </Box>
  )
}
