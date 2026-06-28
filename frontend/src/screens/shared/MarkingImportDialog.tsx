import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
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
import { alpha } from '@mui/material/styles'
import CloudUploadOutlined from '@mui/icons-material/CloudUploadOutlined'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type ProductOption = {
  id: string
  name: string
  sku_code: string
  seller_id: string | null
}

type PreviewGroup = {
  gtin: string
  codes_count: number
  suggested_title: string
}

type PreviewResponse = {
  groups: PreviewGroup[]
  total_codes: number
  invalid_count: number
  duplicates_in_file: number
}

type ImportResponse = {
  accepted_count: number
  skipped_count: number
  pools: { pool_id: string; accepted: number; duplicates: number }[]
}

export type PoolImportSpec = {
  gtin?: string
  title: string
  product_ids: string[]
}

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

export const PRODUCT_SEARCH_INITIAL_LIMIT = 8

export function filterProductsBySearch(
  products: ProductOption[],
  search: string,
): ProductOption[] {
  const needle = search.trim().toLowerCase()
  if (!needle) {
    return products
  }
  return products.filter(
    (row) =>
      row.sku_code.toLowerCase().includes(needle) ||
      row.name.toLowerCase().includes(needle),
  )
}

export function paginateProductSearchResults<T>(
  items: T[],
  showAll: boolean,
  limit = PRODUCT_SEARCH_INITIAL_LIMIT,
): { visible: T[]; total: number; truncated: boolean; limit: number } {
  const total = items.length
  const truncated = total > limit && !showAll
  return {
    visible: truncated ? items.slice(0, limit) : items,
    total,
    truncated,
    limit,
  }
}

export function removeImportFileAt(files: File[], index: number): File[] {
  if (index < 0 || index >= files.length) {
    return files
  }
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
  if (!cleanA || !cleanB) {
    return false
  }
  if (cleanA === cleanB) {
    return true
  }
  const variants = (gtin: string): string[] => {
    const out = [gtin]
    if (gtin.length === 14 && gtin.startsWith('0')) {
      out.push(gtin.slice(1))
    } else if (gtin.length === 13) {
      out.push(`0${gtin}`)
    }
    return out
  }
  const setA = new Set(variants(cleanA))
  return variants(cleanB).some((variant) => setA.has(variant))
}

export function applyPoolContextToGroup(
  group: GroupDraft,
  poolContext: PoolImportContext | null | undefined,
): GroupDraft {
  if (!poolContext || !gtinMatches(group.gtin, poolContext.gtin)) {
    return group
  }
  const productIds =
    poolContext.productIds.length > 0
      ? new Set([...group.productIds, ...poolContext.productIds])
      : group.productIds
  return {
    ...group,
    title: poolContext.title.trim() || group.title,
    productIds,
  }
}

export function mergePreviewGroups(
  prev: GroupDraft[],
  incoming: PreviewGroup[],
  poolContext?: PoolImportContext | null,
): GroupDraft[] {
  const prevByGtin = new Map(prev.map((g) => [g.gtin, g]))
  return incoming.map((g) => {
    const existing = prevByGtin.get(g.gtin)
    if (existing) {
      return applyPoolContextToGroup(
        {
          ...g,
          title: existing.title,
          productIds: existing.productIds,
          productSearch: existing.productSearch,
        },
        poolContext,
      )
    }
    return applyPoolContextToGroup(
      {
        ...g,
        title: g.suggested_title,
        productIds: new Set<string>(),
        productSearch: '',
      },
      poolContext,
    )
  })
}

type Props = {
  open: boolean
  token: string
  sellerId: string
  testIdPrefix: string
  poolContext?: PoolImportContext | null
  onClose: () => void
  onImported: (message: string) => void
  onError?: (message: string | null) => void
}

export function MarkingImportDialog({
  open,
  token,
  sellerId,
  testIdPrefix,
  poolContext = null,
  onClose,
  onImported,
  onError,
}: Props) {
  const [files, setFiles] = useState<File[]>([])
  const [groups, setGroups] = useState<GroupDraft[]>([])
  const [previewMeta, setPreviewMeta] = useState<{
    invalid_count: number
    duplicates_in_file: number
  } | null>(null)
  const [catalog, setCatalog] = useState<ProductOption[]>([])
  const [parseBusy, setParseBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [titleErrorGtins, setTitleErrorGtins] = useState<Set<string>>(new Set())
  const [expandedProductLists, setExpandedProductLists] = useState<Set<string>>(new Set())
  const scrollToTitleGtinRef = useRef<string | null>(null)

  const sellerProducts = useMemo(
    () => catalog.filter((row) => row.seller_id === sellerId),
    [catalog, sellerId],
  )

  const reset = useCallback(() => {
    setFiles([])
    setGroups([])
    setPreviewMeta(null)
    setError(null)
    setTitleErrorGtins(new Set())
    setExpandedProductLists(new Set())
    scrollToTitleGtinRef.current = null
  }, [])

  useEffect(() => {
    if (!open) {
      reset()
      return
    }
    void (async () => {
      const res = await fetch(apiUrl('/products'), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        setCatalog((await res.json()) as ProductOption[])
      }
    })()
  }, [open, reset, token])

  const runPreview = async (picked: File[]) => {
    if (picked.length === 0) {
      return
    }
    setParseBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('seller_id', sellerId)
      for (const file of picked) {
        form.append('files', file)
      }
      const res = await fetch(apiUrl('/operations/marking-codes/import/preview'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        setError(message)
        onError?.(message)
        return
      }
      const data = (await res.json()) as PreviewResponse
      setPreviewMeta({
        invalid_count: data.invalid_count,
        duplicates_in_file: data.duplicates_in_file,
      })
      setGroups((prev) => mergePreviewGroups(prev, data.groups, poolContext))
      onError?.(null)
    } finally {
      setParseBusy(false)
    }
  }

  const onPickFiles = (picked: FileList | null) => {
    if (!picked?.length) {
      return
    }
    const next = [...files, ...Array.from(picked)]
    setFiles(next)
    void runPreview(next)
  }

  const clearPreview = () => {
    setGroups([])
    setPreviewMeta(null)
    setError(null)
    setTitleErrorGtins(new Set())
    setExpandedProductLists(new Set())
    scrollToTitleGtinRef.current = null
  }

  const removeFileAt = (index: number) => {
    if (busy) {
      return
    }
    const next = removeImportFileAt(files, index)
    setFiles(next)
    if (next.length === 0) {
      clearPreview()
      return
    }
    void runPreview(next)
  }

  const updateGroupTitle = (gtin: string, title: string) => {
    setGroups((prev) => prev.map((g) => (g.gtin === gtin ? { ...g, title } : g)))
    if (!isImportGroupTitleMissing(title)) {
      setTitleErrorGtins((prev) => {
        if (!prev.has(gtin)) {
          return prev
        }
        const next = new Set(prev)
        next.delete(gtin)
        return next
      })
    }
  }

  const updateGroupProductSearch = (gtin: string, productSearch: string) => {
    setGroups((prev) => prev.map((g) => (g.gtin === gtin ? { ...g, productSearch } : g)))
    setExpandedProductLists((prev) => {
      if (!prev.has(gtin)) {
        return prev
      }
      const next = new Set(prev)
      next.delete(gtin)
      return next
    })
  }

  const expandProductList = (gtin: string) => {
    setExpandedProductLists((prev) => new Set(prev).add(gtin))
  }

  const toggleGroupProduct = (gtin: string, productId: string) => {
    setGroups((prev) =>
      prev.map((g) => {
        if (g.gtin !== gtin) {
          return g
        }
        const next = new Set(g.productIds)
        if (next.has(productId)) {
          next.delete(productId)
        } else {
          next.add(productId)
        }
        return { ...g, productIds: next }
      }),
    )
  }

  const summary = useMemo(() => {
    const poolCount = groups.length
    const codeCount = groups.reduce((sum, g) => sum + g.codes_count, 0)
    const productCount = new Set(groups.flatMap((g) => [...g.productIds])).size
    return { poolCount, codeCount, productCount }
  }, [groups])

  const upload = async () => {
    if (files.length === 0 || groups.length === 0) {
      return
    }
    const missingTitleGtins = gtinsWithMissingTitle(groups)
    if (missingTitleGtins.length > 0) {
      setTitleErrorGtins(new Set(missingTitleGtins))
      scrollToTitleGtinRef.current = findFirstGtinWithMissingTitle(groups)
      setError('Укажите название пула для каждого GTIN.')
      return
    }
    setUploadBusy(true)
    setError(null)
    setTitleErrorGtins(new Set())
    scrollToTitleGtinRef.current = null
    try {
      const poolsJson: PoolImportSpec[] = groups.map((g) => ({
        gtin: g.gtin,
        title: g.title.trim(),
        product_ids: [...g.productIds],
      }))
      const form = new FormData()
      form.append('seller_id', sellerId)
      form.append('pools_json', JSON.stringify(poolsJson))
      for (const file of files) {
        form.append('files', file)
      }
      const res = await fetch(apiUrl('/operations/marking-codes/import'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        setError(message)
        onError?.(message)
        return
      }
      const data = (await res.json()) as ImportResponse
      const dup = data.skipped_count
      const msg =
        dup > 0
          ? `Загружено ${data.accepted_count}, пропущено ${dup} (дубликаты/ошибки)`
          : `Загружено ${data.accepted_count}`
      onError?.(null)
      onImported(msg)
      onClose()
    } finally {
      setUploadBusy(false)
    }
  }

  const busy = parseBusy || uploadBusy

  useEffect(() => {
    const gtin = scrollToTitleGtinRef.current
    if (!gtin) {
      return
    }
    document
      .querySelector(`[data-testid="${testIdPrefix}-import-group-${gtin}-title-missing"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    scrollToTitleGtinRef.current = null
  }, [titleErrorGtins, testIdPrefix])

  return (
    <Dialog
      open={open}
      onClose={() => !busy && onClose()}
      fullWidth
      maxWidth="md"
      data-testid={`${testIdPrefix}-import-dialog`}
    >
      <DialogTitle>{poolContext ? 'Догрузить коды' : 'Загрузить коды'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          {poolContext ? (
            <Alert severity="info" data-testid={`${testIdPrefix}-import-pool-context`}>
              Догрузка в пул «{poolContext.title}» (GTIN {poolContext.gtin})
              {poolContext.productIds.length > 0
                ? ` · привязано товаров: ${poolContext.productIds.length}`
                : ''}
            </Alert>
          ) : null}
          <Paper
            variant="outlined"
            sx={{
              p: 3,
              textAlign: 'center',
              borderStyle: 'dashed',
              cursor: busy ? 'default' : 'pointer',
            }}
            onClick={() => {
              if (busy) {
                return
              }
              document.getElementById(`${testIdPrefix}-import-file-input`)?.click()
            }}
            data-testid={`${testIdPrefix}-import-dropzone`}
          >
            <CloudUploadOutlined sx={{ fontSize: 40, color: 'text.secondary', mb: 1 }} />
            <Typography variant="body2">
              Перетащите или выберите CSV, TXT или PDF (можно несколько файлов)
            </Typography>
            {files.length > 0 ? (
              <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', justifyContent: 'center', mt: 1 }}>
                {files.map((f, index) => (
                  <Chip
                    key={`${f.name}-${f.size}-${index}`}
                    size="small"
                    label={f.name}
                    onDelete={(event) => {
                      event.stopPropagation()
                      removeFileAt(index)
                    }}
                    data-testid={`${testIdPrefix}-import-file-chip-${index}`}
                  />
                ))}
              </Stack>
            ) : null}
            <input
              id={`${testIdPrefix}-import-file-input`}
              type="file"
              accept=".csv,.txt,.tsv,.pdf"
              multiple
              hidden
              onChange={(e) => onPickFiles(e.target.files)}
              data-testid={`${testIdPrefix}-import-file-input`}
            />
          </Paper>

          {parseBusy ? (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} data-testid={`${testIdPrefix}-import-parsing`}>
              <CircularProgress size={20} />
              <Typography variant="body2">Разбор файла…</Typography>
            </Stack>
          ) : null}

          {error ? (
            <Alert severity="error" data-testid={`${testIdPrefix}-import-error`}>
              {error}
            </Alert>
          ) : null}

          {previewMeta && groups.length > 0 ? (
            <Typography variant="body2" color="text.secondary" data-testid={`${testIdPrefix}-import-preview-meta`}>
              Неформат: {previewMeta.invalid_count} · дубликаты в файле: {previewMeta.duplicates_in_file}
            </Typography>
          ) : null}

          {groups.map((g) => {
            const filteredProducts = filterProductsBySearch(sellerProducts, g.productSearch)
            const showAllProducts = expandedProductLists.has(g.gtin)
            const { visible: visibleProducts, total: productTotal, truncated } =
              paginateProductSearchResults(filteredProducts, showAllProducts)
            const titleMissing = titleErrorGtins.has(g.gtin)

            return (
              <Paper
                key={g.gtin}
                variant="outlined"
                sx={{
                  p: 2,
                  ...(titleMissing
                    ? {
                        borderColor: 'error.main',
                        backgroundColor: (theme) => alpha(theme.palette.error.main, 0.08),
                      }
                    : {}),
                }}
                data-testid={
                  titleMissing
                    ? `${testIdPrefix}-import-group-${g.gtin}-title-missing`
                    : `${testIdPrefix}-import-group-${g.gtin}`
                }
              >
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2">
                    GTIN …{g.gtin.slice(-4)} — {g.codes_count} кодов
                  </Typography>
                  <TextField
                    label="Название пула"
                    value={g.title}
                    onChange={(e) => updateGroupTitle(g.gtin, e.target.value)}
                    error={titleMissing}
                    helperText={titleMissing ? 'Укажите название пула' : undefined}
                    data-testid={`${testIdPrefix}-import-title-${g.gtin}`}
                  />
                  <TextField
                    label="Поиск товаров"
                    value={g.productSearch}
                    onChange={(e) => updateGroupProductSearch(g.gtin, e.target.value)}
                    data-testid={`${testIdPrefix}-import-product-search-${g.gtin}`}
                  />
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell padding="checkbox" />
                          <TableCell>Артикул</TableCell>
                          <TableCell>Название</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {visibleProducts.map((row) => (
                          <TableRow key={`${g.gtin}-${row.id}`}>
                            <TableCell padding="checkbox">
                              <Checkbox
                                checked={g.productIds.has(row.id)}
                                onChange={() => toggleGroupProduct(g.gtin, row.id)}
                                slotProps={{
                                  input: {
                                    'aria-label': `Привязать ${row.sku_code} к GTIN ${g.gtin}`,
                                  },
                                }}
                              />
                            </TableCell>
                            <TableCell>{row.sku_code}</TableCell>
                            <TableCell>{row.name}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  {truncated ? (
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        data-testid={`${testIdPrefix}-import-products-truncated-${g.gtin}`}
                      >
                        Показаны первые {PRODUCT_SEARCH_INITIAL_LIMIT} из {productTotal}
                      </Typography>
                      <Button
                        size="small"
                        onClick={() => expandProductList(g.gtin)}
                        data-testid={`${testIdPrefix}-import-products-show-more-${g.gtin}`}
                      >
                        Показать ещё
                      </Button>
                    </Stack>
                  ) : null}
                  {g.productIds.size === 0 ? (
                    <Chip size="small" color="warning" label="Товары не выбраны — можно привязать позже" />
                  ) : null}
                </Stack>
              </Paper>
            )
          })}

          {groups.length > 0 ? (
            <Box data-testid={`${testIdPrefix}-import-summary`}>
              <Typography variant="body2">
                Будет загружено: {summary.codeCount} кодов в {summary.poolCount} пул(ов), привязка к{' '}
                {summary.productCount} товарам
              </Typography>
            </Box>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={busy || groups.length === 0}
          onClick={() => void upload()}
          data-testid={`${testIdPrefix}-import-submit`}
        >
          Загрузить
        </Button>
      </DialogActions>
    </Dialog>
  )
}
