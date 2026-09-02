import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
} from 'react'
import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { apiUrl } from '../../api'
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import {
  productDisplayMetaFromCatalog,
  type ProductLineDisplayMeta,
  type WbProductCatalogRow,
} from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  boxFillDialogContentSx,
  boxFillDialogPaperSx,
  boxFillQtyCellSx,
  boxFillTableScrollSx,
} from './boxFillDialogLayout'
import { scanErrorMessageRu } from './inboundReceivingHelpers'
import { buildInboundScanProductMap, findInboundScanProductId } from './inboundScanLookup'

type InboundBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

type RequestLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
}

/**
 * Строка таблицы наполнения короба.
 *
 * Вынесена в memo-компонент осознанно: в заявке бывает под триста строк, в каждой
 * фото, ячейки товара и поле количества. Без этого любой скан перерисовывал всю
 * таблицу целиком, и один штрихкод занимал 15–20 секунд на живой приёмке.
 */
const BoxFillRow = memo(function BoxFillRow({
  line,
  meta,
  qtyInBox,
  draftQty,
  highlighted,
  readOnly,
  busy,
  onQtyChange,
  onQtySave,
}: {
  line: RequestLine
  meta: ProductLineDisplayMeta
  qtyInBox: number
  draftQty: string
  highlighted: boolean
  readOnly: boolean
  busy: boolean
  onQtyChange: (productId: string, value: string) => void
  onQtySave: (productId: string, value: string) => void
}) {
  return (
    <TableRow
      data-testid={`ff-inbound-box-add-line-row-${line.product_id}`}
      sx={
        highlighted
          ? {
              backgroundColor: (theme) => alpha(theme.palette.success.main, 0.16),
              boxShadow: (theme) => `inset 0 0 0 1px ${alpha(theme.palette.success.main, 0.6)}`,
            }
          : undefined
      }
    >
      <FfProductLineCells
        meta={meta}
        showPrint={false}
        lineTestIdPrefix={`ff-inbound-box-add-product-${line.product_id}`}
        nameExtra={
          meta.wb_size ? (
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid={`ff-inbound-box-add-size-${line.product_id}`}
              title={`Размер: ${meta.wb_size}`}
            >
              Размер: {meta.wb_size}
            </Typography>
          ) : null
        }
      />
      <TableCell align="right" sx={{ px: 1, verticalAlign: 'top' }}>
        {line.expected_qty}
      </TableCell>
      <TableCell align="right" sx={boxFillQtyCellSx}>
        {readOnly ? (
          <Typography variant="body2" data-testid="ff-inbound-box-add-qty">
            {qtyInBox}
          </Typography>
        ) : (
          <TextField
            type="number"
            size="small"
            value={draftQty}
            onChange={(e) => onQtyChange(line.product_id, e.target.value)}
            slotProps={{
              htmlInput: {
                min: 0,
                'data-testid': 'ff-inbound-box-add-manual-qty',
                onBlur: (e: FocusEvent<HTMLInputElement>) =>
                  onQtySave(line.product_id, e.currentTarget.value),
                onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    onQtySave(line.product_id, e.currentTarget.value)
                  }
                },
              },
            }}
            sx={{ width: 72 }}
            disabled={busy}
          />
        )}
      </TableCell>
    </TableRow>
  )
})

type Props = {
  open: boolean
  onClose: () => void
  requestId: string
  boxId: string
  boxLabel: string
  /**
   * Что наполняем: короб или грузоместо.
   *
   * Процесс у них одинаковый — владелец так и сказал: «в точности по такому же
   * процессу, как и в короба». Отличается только адрес ручки, поэтому диалог
   * один, а не скопированный второй раз.
   */
  containerKind?: 'box' | 'cargo_place'
  readOnly: boolean
  token: string
  requestLines: RequestLine[]
  boxLines: InboundBoxLine[]
  catalogById: Map<string, WbProductCatalogRow>
  onUpdated: () => Promise<void>
}

export function FfInboundBoxAddDialog({
  open,
  onClose,
  requestId,
  boxId,
  boxLabel,
  containerKind,
  readOnly,
  token,
  requestLines,
  boxLines,
  catalogById,
  onUpdated,
}: Props) {
  const authHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scanBarcode, setScanBarcode] = useState('')
  const [localBoxLines, setLocalBoxLines] = useState<InboundBoxLine[]>(boxLines)
  const [lastScannedProductId, setLastScannedProductId] = useState<string | null>(null)
  const [draftQtyByProductId, setDraftQtyByProductId] = useState<Record<string, string>>({})
  const draftQtyRef = useRef(draftQtyByProductId)
  const scanQueueRef = useRef<Promise<void>>(Promise.resolve())

  const qtyInBoxByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const ln of localBoxLines) {
      m.set(ln.product_id, ln.quantity)
    }
    return m
  }, [localBoxLines])

  const scanProductByBarcode = useMemo(
    () => buildInboundScanProductMap(requestLines, catalogById),
    [catalogById, requestLines],
  )

  // Считаем витрину строки один раз на состав заявки, а не на каждый рендер:
  // иначе memo у строки бесполезен — meta каждый раз новый объект.
  const displayMetaByProductId = useMemo(() => {
    const m = new Map<string, ProductLineDisplayMeta>()
    for (const ln of requestLines) {
      m.set(ln.product_id, productDisplayMetaFromCatalog(ln.product_id, ln, catalogById))
    }
    return m
  }, [catalogById, requestLines])

  useEffect(() => {
    setLocalBoxLines(boxLines)
  }, [boxLines])

  useEffect(() => {
    if (!open) {
      setScanBarcode('')
      setLastScannedProductId(null)
      setError(null)
      setDraftQtyByProductId({})
      return
    }
    const quantitiesFromParent = new Map<string, number>(
      boxLines.map((line) => [line.product_id, line.quantity]),
    )
    const next: Record<string, string> = {}
    for (const ln of requestLines) {
      next[ln.product_id] = String(quantitiesFromParent.get(ln.product_id) ?? 0)
    }
    setDraftQtyByProductId(next)
  }, [boxLines, open, requestLines])

  useEffect(() => {
    draftQtyRef.current = draftQtyByProductId
  }, [draftQtyByProductId])

  const saveQty = useCallback(
    async (productId: string, rawOverride?: string) => {
      if (readOnly) {
        return
      }
      const raw = rawOverride ?? draftQtyRef.current[productId] ?? '0'
      const qty = Math.floor(Number(raw))
      if (!Number.isFinite(qty) || qty < 0) {
        setError('Укажите целое количество ≥ 0.')
        return
      }
      const current = qtyInBoxByProductId.get(productId) ?? 0
      if (qty === current) {
        return
      }
      setBusy(true)
      setError(null)
      try {
        const res = await fetch(
          apiUrl(
            `/operations/inbound-intake-requests/${requestId}/${
              containerKind === 'cargo_place' ? 'cargo-places' : 'boxes'
            }/${boxId}/lines/${productId}`,
          ),
          {
            method: 'PUT',
            headers: authHeaders,
            body: JSON.stringify({ quantity: qty }),
          },
        )
        if (!res.ok) {
          setError(scanErrorMessageRu(await readApiErrorMessage(res)))
          return
        }
        await onUpdated()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить количество.')
      } finally {
        setBusy(false)
      }
    },
    [authHeaders, boxId, containerKind, onUpdated, qtyInBoxByProductId, readOnly, requestId],
  )

  // Стабильные обработчики — иначе memo у строки не срабатывает.
  const handleQtyChange = useCallback((productId: string, value: string) => {
    draftQtyRef.current = { ...draftQtyRef.current, [productId]: value }
    setDraftQtyByProductId((prev) => ({ ...prev, [productId]: value }))
  }, [])

  const handleQtySave = useCallback(
    (productId: string, value: string) => {
      void saveQty(productId, value)
    },
    [saveQty],
  )

  const flushPendingQty = useCallback(async () => {
    if (readOnly) {
      return
    }
    for (const ln of requestLines) {
      await saveQty(ln.product_id)
    }
  }, [readOnly, requestLines, saveQty])

  const handleDismiss = async () => {
    // A click on the header close button may happen immediately after a scan.
    // Wait for the serialized scan request before reconciling the parent card,
    // otherwise the closed box can still render as empty until a page reload.
    await scanQueueRef.current
    await flushPendingQty()
    await onUpdated()
    onClose()
  }

  const scanIntoBox = async (rawInput?: string) => {
    if (readOnly) {
      return
    }
    const raw = (rawInput ?? scanBarcode).trim()
    if (!raw) {
      setError('Введите штрихкод.')
      return
    }
    setError(null)
    try {
      const productId = findInboundScanProductId(raw, scanProductByBarcode)
      const res = await fetch(
        apiUrl(
          `/operations/inbound-intake-requests/${requestId}/${
            containerKind === 'cargo_place' ? 'cargo-places' : 'boxes'
          }/${boxId}/scan`,
        ),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ barcode: raw, product_id: productId }),
        },
      )
      if (!res.ok) {
        setError(scanErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      // Две ручки на одно действие отвечают по-разному: скан в короб отдаёт
      // строку товара, скан в грузоместо — весь объект со списком строк.
      // Читаем оба вида, иначе у грузоместа идентификатор товара оказывается
      // пустым и колонка «В коробе» остаётся пустой при принятом скане.
      const payload = (await res.json()) as
        | InboundBoxLine
        | { lines?: InboundBoxLine[] }
      const scannedLine =
        'product_id' in payload && payload.product_id
          ? (payload as InboundBoxLine)
          : ((payload as { lines?: InboundBoxLine[] }).lines ?? []).find(
              (line) => line.product_id === productId,
            )
      if (!scannedLine) {
        setError('Сервер принял скан, но не вернул строку товара.')
        return
      }
      setLocalBoxLines((current) => {
        const exists = current.some((line) => line.product_id === scannedLine.product_id)
        return exists
          ? current.map((line) => (line.product_id === scannedLine.product_id ? scannedLine : line))
          : [...current, scannedLine]
      })
      setDraftQtyByProductId((current) => ({
        ...current,
        [scannedLine.product_id]: String(scannedLine.quantity),
      }))
      setLastScannedProductId(scannedLine.product_id)
      setScanBarcode('')
      // The POST response is authoritative for this box. Refresh the heavy parent
      // document once when the operator presses "Готово", not after every barcode.
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    }
  }

  const enqueueScanIntoBox = (rawInput?: string): Promise<void> => {
    const next = scanQueueRef.current.then(
      () => scanIntoBox(rawInput),
      () => scanIntoBox(rawInput),
    )
    scanQueueRef.current = next.catch(() => undefined)
    return next
  }

  // Оператор должен видеть, что скан попал именно туда, куда он думает.
  // Хотфикс 22.08 убрал эхо штрихкода в поле, а подсветка отсканированной строки
  // в таблице на две-три сотни позиций почти всегда оказывается вне экрана —
  // в итоге на складе скан перестал давать какой-либо видимый отклик.
  useBarcodeScanner({
    enabled: open && !readOnly,
    onScan: (code) => {
      setScanBarcode(code)
      void enqueueScanIntoBox(code)
    },
  })

  useEffect(() => {
    if (!lastScannedProductId) {
      return
    }
    document
      .querySelector(`[data-testid="ff-inbound-box-add-line-row-${lastScannedProductId}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [lastScannedProductId])

  return (
    <Dialog
      open={open}
      onClose={() => void handleDismiss()}
      maxWidth={false}
      fullWidth
      data-testid="ff-inbound-box-add-dialog"
      slotProps={{ paper: { sx: boxFillDialogPaperSx } }}
    >
      <DialogTitle component="div" sx={{ pr: 6, flexShrink: 0 }} data-testid="ff-inbound-box-add-title">
        <Typography component="span" variant="h6" sx={{ display: 'block', fontWeight: 700 }}>
          {containerKind === 'cargo_place' ? 'Наполнить грузоместо' : 'Наполнить короб'}
        </Typography>
        <Typography
          variant="body2"
          sx={{ fontWeight: 700, mt: 0.5 }}
          data-testid="ff-inbound-box-add-box-label"
        >
          {boxLabel}
        </Typography>
        <IconButton
          aria-label="Скрыть окно"
          onClick={() => void handleDismiss()}
          sx={{ position: 'absolute', right: 8, top: 8 }}
          data-testid="ff-inbound-box-add-close"
        >
          <CloseOutlined />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={boxFillDialogContentSx}>
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0 }}>
          {readOnly ? (
            <Alert severity="info">Приёмка завершена — состав короба только для просмотра.</Alert>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid="ff-inbound-box-add-error">
              {error}
            </Alert>
          ) : null}

          {!readOnly ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexShrink: 0 }}>
              <TextField
                size="small"
                label="Штрихкод товара"
                value={scanBarcode}
                onChange={(e) => setScanBarcode(e.target.value)}
                disabled={busy}
                fullWidth
                autoFocus
                slotProps={{
                  // onKeyDown вешаем на само поле ввода: MUI пробрасывает внутрь
                  // только onChange, onBlur и onFocus, а остальное садится на
                  // внешнюю обёртку — и Enter в сканере не срабатывал.
                  htmlInput: {
                    'data-testid': 'ff-inbound-box-add-scan-input',
                    onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        void enqueueScanIntoBox()
                      }
                    },
                  },
                }}
              />
              <Button
                variant="contained"
                onClick={() => void enqueueScanIntoBox()}
                disabled={busy || !scanBarcode.trim()}
                data-testid="ff-inbound-box-add-scan-submit"
                sx={{ flexShrink: 0 }}
              >
                Скан
              </Button>
            </Stack>
          ) : null}

          <Box sx={boxFillTableScrollSx}>
            <Table size="small" stickyHeader data-testid="ff-inbound-box-add-table">
              <TableHead>
                <TableRow>
                  <FfProductTableHeadCells showPrint={false} />
                  <TableCell align="right" sx={{ width: 80, whiteSpace: 'nowrap', px: 1 }}>
                    Заявлено
                  </TableCell>
                  <TableCell align="right" sx={boxFillQtyCellSx}>
                    В коробе
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {requestLines.map((ln) => (
                  <BoxFillRow
                    key={ln.id}
                    line={ln}
                    meta={displayMetaByProductId.get(ln.product_id) as ProductLineDisplayMeta}
                    qtyInBox={qtyInBoxByProductId.get(ln.product_id) ?? 0}
                    draftQty={draftQtyByProductId[ln.product_id] ?? '0'}
                    highlighted={lastScannedProductId === ln.product_id}
                    readOnly={readOnly}
                    busy={busy}
                    onQtyChange={handleQtyChange}
                    onQtySave={handleQtySave}
                  />
                ))}
              </TableBody>
            </Table>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexShrink: 0 }}>
        <Button
          variant="contained"
          onClick={() => void handleDismiss()}
          disabled={busy}
          data-testid="ff-inbound-box-add-dismiss"
        >
          Готово
        </Button>
      </DialogActions>
    </Dialog>
  )
}
