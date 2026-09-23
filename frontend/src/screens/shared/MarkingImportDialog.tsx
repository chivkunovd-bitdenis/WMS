import { ErrorBoundary } from '../../components/errors/ErrorBoundary'
import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TextField, Typography,
} from '@mui/material'
import CloudUploadOutlined from '@mui/icons-material/CloudUploadOutlined'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type ImportCatalogRow = {
  id: string
  name: string
  sku_code: string
  seller_id: string | null
  seller_name?: string | null
  requires_honest_sign: boolean
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  wb_color?: string | null
  wb_brand?: string | null
  wb_composition?: string | null
}

async function fetchImportCatalog(
  token: string,
  sellerId: string,
  mode: 'ff' | 'seller',
): Promise<ImportCatalogRow[]> {
  const headers = { Authorization: `Bearer ${token}` }
  const path = mode === 'seller'
    ? '/products/wb-catalog'
    : `/products/linked-wb-catalog?seller_id=${encodeURIComponent(sellerId)}`
  const res = await fetch(apiUrl(path), { headers })
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
  return (await res.json()) as ImportCatalogRow[]
}

type PreviewGroup = { gtin: string; codes_count: number; suggested_title: string }
type PreviewResponse = {
  groups: PreviewGroup[]
  total_codes: number
  invalid_count: number
  duplicates_in_file: number
}
type ImportResponse = { accepted_count: number; skipped_count: number }
type AutoProductGroup = {
  product_id: string
  sku: string
  product_name: string
  size: string | null
  barcode: string | null
  loaded_count: number
}
type AutoUnmatchedRow = {
  key: string
  marking_code: string
  article: string | null
  size: string | null
  reason: string
  eligible_for_assignment: boolean
  has_label_artifact: boolean
}
export type AutoImportResponse = {
  import_id: string
  document_number: string
  groups: AutoProductGroup[]
  unmatched: AutoUnmatchedRow[]
}
type AssignResponse = {
  import_id: string
  document_number: string
  product: AutoProductGroup
  assigned_keys: string[]
}

export type PoolImportSpec = { gtin?: string; title: string; product_ids: string[] }
export type PoolImportContext = {
  gtin: string
  title: string
  productIds: string[]
}
type GroupDraft = PreviewGroup & {
  title: string
  productIds: Set<string>
  productSearch: string
}
type Stage = 'picker' | 'auto-result' | 'auto-error' | 'assign'

export const PRODUCT_SEARCH_INITIAL_LIMIT = 8

export function filterProductsBySearch(
  products: ImportCatalogRow[],
  search: string,
): ImportCatalogRow[] {
  const needle = search.trim().toLowerCase()
  if (!needle) return products
  return products.filter((row) => {
    const nm = row.wb_nm_id != null ? String(row.wb_nm_id) : ''
    const barcodes = row.wb_barcodes.join(' ').toLowerCase()
    const hay = `${row.sku_code} ${row.wb_vendor_code ?? ''} ${row.name} ${nm} ${barcodes}`.toLowerCase()
    return hay.includes(needle)
  })
}

export function paginateProductSearchResults<T>(
  items: T[],
  showAll: boolean,
  limit = PRODUCT_SEARCH_INITIAL_LIMIT,
): { visible: T[]; total: number; truncated: boolean; limit: number } {
  const total = items.length
  const truncated = total > limit && !showAll
  return { visible: truncated ? items.slice(0, limit) : items, total, truncated, limit }
}

export function removeImportFileAt(files: File[], index: number): File[] {
  if (index < 0 || index >= files.length) return files
  return files.filter((_, i) => i !== index)
}
export function isImportGroupTitleMissing(title: string): boolean {
  return title.trim().length === 0
}
export function gtinsWithMissingTitle(groups: { gtin: string; title: string }[]): string[] {
  return groups.filter((g) => isImportGroupTitleMissing(g.title)).map((g) => g.gtin)
}
export function findFirstGtinWithMissingTitle(
  groups: { gtin: string; title: string }[],
): string | null {
  return groups.find((g) => isImportGroupTitleMissing(g.title))?.gtin ?? null
}
export function gtinMatches(a: string, b: string): boolean {
  const cleanA = a.trim()
  const cleanB = b.trim()
  if (!cleanA || !cleanB) return false
  if (cleanA === cleanB) return true
  const variants = (gtin: string): string[] => {
    const out = [gtin]
    if (gtin.length === 14 && gtin.startsWith('0')) out.push(gtin.slice(1))
    else if (gtin.length === 13) out.push(`0${gtin}`)
    return out
  }
  const setA = new Set(variants(cleanA))
  return variants(cleanB).some((variant) => setA.has(variant))
}
export function applyPoolContextToGroup(
  group: GroupDraft,
  poolContext: PoolImportContext | null | undefined,
): GroupDraft {
  if (!poolContext || !gtinMatches(group.gtin, poolContext.gtin)) return group
  return {
    ...group,
    title: poolContext.title.trim() || group.title,
    productIds: poolContext.productIds.length > 0
      ? new Set([...group.productIds, ...poolContext.productIds])
      : group.productIds,
  }
}
function findExistingGroupByGtin(prev: GroupDraft[], gtin: string): GroupDraft | undefined {
  return prev.find((g) => gtinMatches(g.gtin, gtin))
}
export function mergePreviewGroups(
  prev: GroupDraft[],
  incoming: PreviewGroup[],
  poolContext?: PoolImportContext | null,
): GroupDraft[] {
  return incoming.map((g) => {
    const existing = findExistingGroupByGtin(prev, g.gtin)
    if (existing) return { ...g, title: existing.title, productIds: existing.productIds, productSearch: existing.productSearch }
    return applyPoolContextToGroup(
      { ...g, title: g.suggested_title, productIds: new Set<string>(), productSearch: '' },
      poolContext,
    )
  })
}

type Props = {
  open: boolean
  token: string
  sellerId: string
  catalogMode?: 'ff' | 'seller'
  testIdPrefix: string
  poolContext?: PoolImportContext | null
  onClose: () => void
  onImported: (message: string) => void
  onError?: (message: string | null) => void
}

function newRequestId(): string { return crypto.randomUUID() }
function appendFiles(form: FormData, files: File[]): void {
  for (const file of files) form.append('files', file)
}

type AutomaticImportAttempt =
  | { stage: 'auto-result'; data: AutoImportResponse }
  | { stage: 'auto-error'; message: string }
  | null

export async function runAutomaticImportAttempt({
  files, previewComplete, selectedProductCount, sellerId, token, requestId,
  fetchImpl = fetch,
}: {
  files: File[]
  previewComplete: boolean
  selectedProductCount: number
  sellerId: string
  token: string
  requestId: string
  fetchImpl?: typeof fetch
}): Promise<AutomaticImportAttempt> {
  if (files.length === 0 || !previewComplete || selectedProductCount > 0) return null
  try {
    const form = new FormData()
    form.append('seller_id', sellerId)
    form.append('request_id', requestId)
    appendFiles(form, files)
    const res = await fetchImpl(apiUrl('/operations/marking-codes/import/auto'), {
      method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
    })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    return { stage: 'auto-result', data: (await res.json()) as AutoImportResponse }
  } catch (err) {
    return {
      stage: 'auto-error',
      message: err instanceof Error ? err.message : 'Распознавание не завершено.',
    }
  }
}

export function keepAssignmentRequestId(
  current: string | null,
  create: () => string = newRequestId,
): string {
  return current ?? create()
}

export function MarkingImportDialog(props: Props) {
  return (
    <ErrorBoundary component="MarkingImportDialog" resetKey={String(props.open)}>
      <MarkingImportDialogContent {...props} />
    </ErrorBoundary>
  )
}

function MarkingImportDialogContent({
  open, token, sellerId, catalogMode = 'ff', testIdPrefix, poolContext = null,
  onClose, onImported, onError,
}: Props) {
  const [stage, setStage] = useState<Stage>('picker')
  const [files, setFiles] = useState<File[]>([])
  const [groups, setGroups] = useState<GroupDraft[]>([])
  const [catalog, setCatalog] = useState<ImportCatalogRow[]>([])
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set())
  const [productSearch, setProductSearch] = useState('')
  const [showAllProducts, setShowAllProducts] = useState(false)
  const [previewComplete, setPreviewComplete] = useState(false)
  const [parseBusy, setParseBusy] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoResult, setAutoResult] = useState<AutoImportResponse | null>(null)
  const [selectedUnmatchedKeys, setSelectedUnmatchedKeys] = useState<Set<string>>(new Set())
  const [assignmentProductId, setAssignmentProductId] = useState<string | null>(null)
  const [assignmentRequestId, setAssignmentRequestId] = useState<string | null>(null)
  const previewAbortRef = useRef<AbortController | null>(null)
  const autoRequestIdRef = useRef(newRequestId())

  const sellerCatalogProducts = useMemo(
    () => catalog.filter((row) => row.seller_id == null || row.seller_id === sellerId),
    [catalog, sellerId],
  )
  const sellerProducts = useMemo(
    () => sellerCatalogProducts.filter((row) => row.requires_honest_sign),
    [sellerCatalogProducts],
  )

  const reset = useCallback(() => {
    previewAbortRef.current?.abort()
    previewAbortRef.current = null
    setStage('picker')
    setFiles([])
    setGroups([])
    setSelectedProductIds(new Set(poolContext?.productIds ?? []))
    setProductSearch('')
    setShowAllProducts(false)
    setPreviewComplete(false)
    setParseBusy(false)
    setActionBusy(false)
    setError(null)
    setAutoResult(null)
    setSelectedUnmatchedKeys(new Set())
    setAssignmentProductId(null)
    setAssignmentRequestId(null)
    autoRequestIdRef.current = newRequestId()
  }, [poolContext])

  useEffect(() => {
    if (!open) { reset(); return }
    reset()
    void (async () => {
      try { setCatalog(await fetchImportCatalog(token, sellerId, catalogMode)) }
      catch (err) { setError(err instanceof Error ? err.message : 'Не удалось загрузить каталог товаров.') }
    })()
  }, [catalogMode, open, reset, sellerId, token])
  useEffect(() => () => previewAbortRef.current?.abort(), [])

  const runPreview = async (picked: File[]) => {
    previewAbortRef.current?.abort()
    if (picked.length === 0) { setGroups([]); setPreviewComplete(false); return }
    const controller = new AbortController()
    previewAbortRef.current = controller
    setParseBusy(true)
    setPreviewComplete(false)
    setError(null)
    setAutoResult(null)
    setStage('picker')
    autoRequestIdRef.current = newRequestId()
    try {
      const form = new FormData()
      form.append('seller_id', sellerId)
      appendFiles(form, picked)
      const res = await fetch(apiUrl('/operations/marking-codes/import/preview'), {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const data = (await res.json()) as PreviewResponse
      if (!controller.signal.aborted) {
        setGroups((prev) => mergePreviewGroups(prev, data.groups, poolContext))
        setPreviewComplete(true)
        onError?.(null)
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message = err instanceof Error ? err.message : 'Не удалось разобрать файл.'
      setPreviewComplete(false); setError(message); onError?.(message)
    } finally {
      if (previewAbortRef.current === controller) {
        previewAbortRef.current = null; setParseBusy(false)
      }
    }
  }

  const onPickFiles = (picked: FileList | null) => {
    if (!picked?.length) return
    const next = [...files, ...Array.from(picked)]
    setFiles(next); void runPreview(next)
  }
  const removeFile = (index: number) => {
    if (parseBusy || actionBusy) return
    const next = removeImportFileAt(files, index)
    setFiles(next); void runPreview(next)
  }
  const toggleProduct = (productId: string) => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev)
      if (next.has(productId)) next.delete(productId); else next.add(productId)
      return next
    })
  }

  const manualUpload = async () => {
    if (files.length === 0 || groups.length === 0 || selectedProductIds.size === 0) return
    setActionBusy(true); setError(null)
    try {
      const poolsJson: PoolImportSpec[] = groups.map((group) => ({
        gtin: group.gtin,
        title: poolContext && gtinMatches(group.gtin, poolContext.gtin)
          ? poolContext.title : group.suggested_title,
        product_ids: [...selectedProductIds],
      }))
      const form = new FormData()
      form.append('seller_id', sellerId)
      form.append('pools_json', JSON.stringify(poolsJson))
      appendFiles(form, files)
      const res = await fetch(apiUrl('/operations/marking-codes/import'), {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const data = (await res.json()) as ImportResponse
      const message = data.skipped_count > 0
        ? `Загружено ${data.accepted_count}, пропущено ${data.skipped_count} (дубликаты/ошибки)`
        : `Загружено ${data.accepted_count}`
      onError?.(null); onImported(message); onClose()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить коды.'
      setError(message); onError?.(message)
    } finally { setActionBusy(false) }
  }

  const autoUpload = async () => {
    if (files.length === 0 || !previewComplete || selectedProductIds.size > 0) return
    setActionBusy(true); setError(null)
    const outcome = await runAutomaticImportAttempt({
      files,
      previewComplete,
      selectedProductCount: selectedProductIds.size,
      sellerId,
      token,
      requestId: autoRequestIdRef.current,
    })
    if (outcome?.stage === 'auto-result') {
      const data = outcome.data
      setAutoResult(data); setSelectedUnmatchedKeys(new Set()); setStage('auto-result')
      onError?.(null)
      onImported(`Загружено ${data.groups.reduce((sum, row) => sum + row.loaded_count, 0)} КИЗ`)
    } else if (outcome?.stage === 'auto-error') {
      const message = outcome.message
      setError(message); setStage('auto-error'); onError?.(message)
    }
    setActionBusy(false)
  }

  const toggleUnmatched = (row: AutoUnmatchedRow) => {
    if (!row.eligible_for_assignment) return
    setSelectedUnmatchedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(row.key)) next.delete(row.key); else next.add(row.key)
      return next
    })
  }
  const toggleAllUnmatched = () => {
    const eligible = (autoResult?.unmatched ?? [])
      .filter((row) => row.eligible_for_assignment).map((row) => row.key)
    const allSelected = eligible.length > 0 && eligible.every((key) => selectedUnmatchedKeys.has(key))
    setSelectedUnmatchedKeys(allSelected ? new Set() : new Set(eligible))
  }
  const beginAssignment = () => {
    if (selectedUnmatchedKeys.size === 0) return
    if (assignmentRequestId === null) {
      setAssignmentProductId(null); setProductSearch(''); setShowAllProducts(false)
    }
    setAssignmentRequestId((current) => keepAssignmentRequestId(current))
    setError(null); setStage('assign')
  }

  const confirmAssignment = async () => {
    if (!assignmentProductId || !assignmentRequestId || selectedUnmatchedKeys.size === 0) return
    setActionBusy(true); setError(null)
    try {
      const form = new FormData()
      form.append('seller_id', sellerId)
      form.append('request_id', assignmentRequestId)
      form.append('product_id', assignmentProductId)
      form.append('row_keys_json', JSON.stringify([...selectedUnmatchedKeys]))
      appendFiles(form, files)
      const res = await fetch(apiUrl('/operations/marking-codes/import/assign'), {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const data = (await res.json()) as AssignResponse
      const assigned = new Set(data.assigned_keys)
      setAutoResult((prev) => {
        if (!prev) return prev
        const exists = prev.groups.some((row) => row.product_id === data.product.product_id)
        const nextGroups = exists
          ? prev.groups.map((row) => row.product_id === data.product.product_id
              ? { ...row, loaded_count: row.loaded_count + data.product.loaded_count } : row)
          : [...prev.groups, data.product]
        return { ...prev, groups: nextGroups, unmatched: prev.unmatched.filter((row) => !assigned.has(row.key)) }
      })
      setSelectedUnmatchedKeys(new Set()); setAssignmentProductId(null)
      setAssignmentRequestId(null); setStage('auto-result')
      onImported(`Добавлено к товару: ${data.assigned_keys.length} КИЗ`); onError?.(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось добавить КИЗ к товару.'
      setError(message); onError?.(message)
    } finally { setActionBusy(false) }
  }

  const downloadUnmatched = async () => {
    if (
      !autoResult
      || autoResult.unmatched.length === 0
      || autoResult.unmatched.some((row) => !row.has_label_artifact)
    ) return
    setActionBusy(true); setError(null)
    try {
      const form = new FormData()
      form.append('seller_id', sellerId)
      form.append('row_keys_json', JSON.stringify(autoResult.unmatched.map((row) => row.key)))
      appendFiles(form, files)
      const res = await fetch(apiUrl('/operations/marking-codes/import/unmatched-pdf'), {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const url = URL.createObjectURL(await res.blob())
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = 'WMS-476-nepodgruzhennye-kizy.pdf'
      document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось скачать PDF.'
      setError(message); onError?.(message)
    } finally { setActionBusy(false) }
  }

  const busy = parseBusy || actionBusy
  const pickerReady = files.length > 0 && previewComplete && !parseBusy

  return (
    <Dialog open={open} onClose={() => !busy && onClose()} fullWidth maxWidth="md"
      data-testid={`${testIdPrefix}-import-dialog`}>
      <DialogTitle>Загрузка КИЗ</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          {stage === 'picker' ? (
            <>
              <Paper variant="outlined" sx={{ p: 3, textAlign: 'center', borderStyle: 'dashed', cursor: busy ? 'default' : 'pointer' }}
                onClick={() => !busy && document.getElementById(`${testIdPrefix}-import-file-input`)?.click()}
                data-testid={`${testIdPrefix}-import-dropzone`}>
                <CloudUploadOutlined sx={{ fontSize: 40, color: 'text.secondary', mb: 1 }} />
                <Typography variant="body2">Перетащите PDF или CSV из «Честного знака»</Typography>
                {files.length > 0 ? (
                  <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', justifyContent: 'center', mt: 1 }}>
                    {files.map((file, index) => (
                      <Chip key={`${file.name}-${file.size}-${index}`} size="small" label={file.name}
                        onDelete={(event) => { event.stopPropagation(); removeFile(index) }} />
                    ))}
                  </Stack>
                ) : null}
                <input id={`${testIdPrefix}-import-file-input`} type="file" accept=".csv,.txt,.tsv,.pdf"
                  multiple hidden data-testid={`${testIdPrefix}-import-file-input`}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    onPickFiles(event.target.files); event.target.value = ''
                  }} />
              </Paper>
              {parseBusy ? <BusyLine text="Разбор файла…" testId={`${testIdPrefix}-import-parsing`} /> : null}
              {error ? <Alert severity="error">{error}</Alert> : null}
              {pickerReady && groups.length > 0 ? (
                <ProductPicker products={sellerProducts} allCatalogProducts={sellerCatalogProducts}
                  search={productSearch} showAll={showAllProducts} selectedIds={selectedProductIds}
                  onSearch={(value) => { setProductSearch(value); setShowAllProducts(false) }}
                  onShowAll={() => setShowAllProducts(true)} onToggle={toggleProduct}
                  testIdPrefix={`${testIdPrefix}-import`} />
              ) : null}
              {actionBusy ? <BusyLine text={selectedProductIds.size > 0
                ? 'Загружаем коды на выбранные товары…' : 'Распознаём коды…'} /> : null}
            </>
          ) : null}
          {stage === 'auto-result' && autoResult ? (
            <AutoResult result={autoResult} selectedKeys={selectedUnmatchedKeys} busy={actionBusy}
              onToggle={toggleUnmatched} onToggleAll={toggleAllUnmatched} onAssign={beginAssignment}
              onDownload={() => void downloadUnmatched()} error={error} testIdPrefix={testIdPrefix} />
          ) : null}
          {stage === 'assign' ? (
            <>
              <Alert severity="info">Выбрано КИЗ: <strong>{selectedUnmatchedKeys.size}</strong>. Выберите один товар для добавления.</Alert>
              {error ? <Alert severity="error">{error}</Alert> : null}
              <ProductPicker products={sellerProducts} allCatalogProducts={sellerCatalogProducts}
                search={productSearch} showAll={showAllProducts}
                selectedIds={new Set(assignmentProductId ? [assignmentProductId] : [])}
                onSearch={(value) => { setProductSearch(value); setShowAllProducts(false) }}
                onShowAll={() => setShowAllProducts(true)}
                onToggle={(productId) => setAssignmentProductId((current) => current === productId ? null : productId)}
                testIdPrefix={`${testIdPrefix}-assignment`} />
              {actionBusy ? <BusyLine text="Добавляем КИЗ к товару…" /> : null}
            </>
          ) : null}
          {stage === 'auto-error' ? (
            <>
              <Alert severity="error"><strong>Распознавание не завершено.</strong> {error ?? 'Попробуйте повторить или выберите другой файл.'}</Alert>
              <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
                <Typography variant="caption" color="text.secondary">Файлы, с которыми не получилось:</Typography>
                <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
                  {files.map((file, index) => <Chip key={`${file.name}-${index}`} size="small" label={file.name} />)}
                </Stack>
                <Stack direction="row" spacing={1}>
                  <Button variant="contained" onClick={() => void autoUpload()} disabled={actionBusy}>Попробовать снова</Button>
                  <Button variant="outlined" onClick={reset} disabled={actionBusy}>Выбрать другой файл</Button>
                </Stack>
              </Stack></Paper>
            </>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        {stage === 'picker' ? <>
          <Button onClick={onClose} disabled={busy}>Отмена</Button>
          <Button variant="contained" disabled={!pickerReady || busy}
            onClick={() => void (selectedProductIds.size > 0 ? manualUpload() : autoUpload())}
            data-testid={`${testIdPrefix}-import-submit`}>
            {selectedProductIds.size > 0 ? 'Загрузить' : 'Распознать автоматически'}
          </Button>
        </> : null}
        {stage === 'auto-result' ? <>
          <Button variant="outlined" onClick={reset} disabled={busy}>Загрузить ещё</Button>
          <Button variant="contained" onClick={onClose} disabled={busy}>Готово</Button>
        </> : null}
        {stage === 'assign' ? <>
          <Button variant="outlined" disabled={busy} onClick={() => {
            setError(null); setStage('auto-result')
          }}>Назад</Button>
          <Button variant="contained" disabled={!assignmentProductId || busy}
            onClick={() => void confirmAssignment()}>Добавить к выбранному товару</Button>
        </> : null}
        {stage === 'auto-error' ? <Button onClick={onClose} disabled={busy}>Закрыть</Button> : null}
      </DialogActions>
    </Dialog>
  )
}

function BusyLine({ text, testId }: { text: string; testId?: string }) {
  return <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} data-testid={testId}>
    <CircularProgress size={20} /><Typography variant="body2">{text}</Typography>
  </Stack>
}

function ProductPicker({ products, allCatalogProducts, search, showAll, selectedIds,
  onSearch, onShowAll, onToggle, testIdPrefix }: {
  products: ImportCatalogRow[]
  allCatalogProducts: ImportCatalogRow[]
  search: string
  showAll: boolean
  selectedIds: Set<string>
  onSearch: (value: string) => void
  onShowAll: () => void
  onToggle: (productId: string) => void
  testIdPrefix: string
}) {
  const filtered = filterProductsBySearch(products, search)
  const { visible, total, truncated } = paginateProductSearchResults(filtered, showAll)
  return <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
    <TextField label="Поиск товаров" placeholder="Артикул, название или штрихкод" value={search}
      onChange={(event) => onSearch(event.target.value)} data-testid={`${testIdPrefix}-product-search`} />
    <TableContainer sx={{ maxHeight: 360 }}><Table size="small" stickyHeader><TableBody>
      {visible.map((row) => <TableRow key={row.id} hover selected={selectedIds.has(row.id)}
        onClick={() => onToggle(row.id)} sx={{ cursor: 'pointer' }}
        data-testid={`${testIdPrefix}-product-row-${row.id}`}>
        <TableCell padding="checkbox"><Checkbox checked={selectedIds.has(row.id)}
          slotProps={{ input: { 'aria-label': `${row.sku_code} ${row.name}` } }} /></TableCell>
        <TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.sku_code}</Typography>
          <Typography variant="caption" color="text.secondary">{row.name}</Typography></TableCell>
      </TableRow>)}
      {visible.length === 0 ? <TableRow><TableCell colSpan={2}><Typography variant="body2" color="text.secondary">
        {products.length === 0 && allCatalogProducts.length > 0
          ? 'У этого селлера нет товаров с признаком «Нужен Честный знак при упаковке».'
          : products.length === 0 ? 'У этого селлера нет товаров для привязки.'
            : 'По поиску товары не найдены. Измените запрос или очистите поиск.'}
      </Typography></TableCell></TableRow> : null}
    </TableBody></Table></TableContainer>
    {truncated ? <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <Typography variant="caption" color="text.secondary">Показаны первые {PRODUCT_SEARCH_INITIAL_LIMIT} из {total}
        {selectedIds.size > 0 ? ` · выбрано ${selectedIds.size}` : ''}</Typography>
      <Button size="small" onClick={onShowAll}>Показать ещё</Button>
    </Stack> : null}
  </Stack></Paper>
}

function AutoResult({ result, selectedKeys, busy, onToggle, onToggleAll, onAssign,
  onDownload, error, testIdPrefix }: {
  result: AutoImportResponse
  selectedKeys: Set<string>
  busy: boolean
  onToggle: (row: AutoUnmatchedRow) => void
  onToggleAll: () => void
  onAssign: () => void
  onDownload: () => void
  error: string | null
  testIdPrefix: string
}) {
  const loaded = result.groups.reduce((sum, row) => sum + row.loaded_count, 0)
  const eligible = result.unmatched.filter((row) => row.eligible_for_assignment)
  const allSelected = eligible.length > 0 && eligible.every((row) => selectedKeys.has(row.key))
  const canDownload = result.unmatched.length > 0
    && result.unmatched.every((row) => row.has_label_artifact)
  return <>
    <Alert severity="success"><strong>Загружено {loaded} КИЗ</strong> · привязано к {result.groups.length} товарам.</Alert>
    {error ? <Alert severity="error">{error}</Alert> : null}
    <TableContainer component={Paper} variant="outlined"><Table size="small" data-testid={`${testIdPrefix}-auto-groups`}>
      <TableHead><TableRow><TableCell>Артикул</TableCell><TableCell>Размер</TableCell>
        <TableCell>Штрихкод</TableCell><TableCell align="right">Загружено КИЗ</TableCell></TableRow></TableHead>
      <TableBody>{result.groups.map((row) => <TableRow key={row.product_id}>
        <TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.sku}</Typography>
          <Typography variant="caption" color="text.secondary">{row.product_name}</Typography></TableCell>
        <TableCell>{row.size ?? '—'}</TableCell><TableCell sx={{ fontFamily: 'monospace' }}>{row.barcode ?? '—'}</TableCell>
        <TableCell align="right"><strong>{row.loaded_count}</strong></TableCell>
      </TableRow>)}</TableBody>
    </Table></TableContainer>
    <Paper variant="outlined" sx={{ borderColor: 'error.light', overflow: 'hidden' }}><Stack spacing={1.5} sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Typography variant="subtitle2">Не подгружено — {result.unmatched.length} КИЗ</Typography>
        {result.unmatched.length > 0 ? <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          <Button variant="contained" size="small" disabled={selectedKeys.size === 0 || busy} onClick={onAssign}>Добавить к товару</Button>
          {canDownload ? <Button variant="outlined" color="error" size="small" disabled={busy}
            onClick={onDownload}>Скачать PDF с неподгруженными КИЗами</Button> : null}
        </Stack> : null}
      </Stack>
      {result.unmatched.length === 0
        ? <Typography variant="caption" color="text.secondary">В файле не осталось этикеток без привязки — все КИЗ распознаны.</Typography>
        : <><Typography variant="caption" color="text.secondary">Успешная часть уже сохранена. Эти коды можно перепроверить и загрузить вручную позже.</Typography>
          <TableContainer><Table size="small" data-testid={`${testIdPrefix}-auto-unmatched`}>
            <TableHead><TableRow><TableCell padding="checkbox"><Checkbox checked={allSelected} disabled={eligible.length === 0}
              onChange={onToggleAll} slotProps={{ input: { 'aria-label': 'Выбрать все доступные КИЗ' } }} /></TableCell>
              <TableCell>Код маркировки</TableCell><TableCell>Артикул</TableCell><TableCell>Размер</TableCell><TableCell>Причина</TableCell>
            </TableRow></TableHead>
            <TableBody>{result.unmatched.map((row) => <TableRow key={row.key} sx={{ opacity: row.eligible_for_assignment ? 1 : 0.65 }}>
              <TableCell padding="checkbox"><Checkbox checked={selectedKeys.has(row.key)} disabled={!row.eligible_for_assignment}
                onChange={() => onToggle(row)} slotProps={{ input: { 'aria-label': `Выбрать КИЗ ${row.marking_code}` } }} /></TableCell>
              <TableCell sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{row.marking_code}</TableCell>
              <TableCell>{row.article ?? '—'}</TableCell><TableCell>{row.size ?? '—'}</TableCell>
              <TableCell><Typography variant="body2">{row.reason}</Typography>{!row.eligible_for_assignment
                ? <Typography variant="caption" color="error">Нельзя добавить к товару</Typography> : null}</TableCell>
            </TableRow>)}</TableBody>
          </Table></TableContainer></>}
    </Stack></Paper>
  </>
}
