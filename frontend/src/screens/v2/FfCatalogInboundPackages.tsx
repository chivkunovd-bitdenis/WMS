import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
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
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../api'
import { ProductBarcodeCell } from '../../components/ProductBarcodeCell'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type SourceDocument = {
  kind: string
  id: string
  number: string | null
  date: string
}

type InboundPackageLine = {
  product_id: string
  remaining_qty: number
  name: string
  sku_code: string
  wb_vendor_code: string | null
  wb_barcode: string | null
  wb_size: string | null
  seller_name: string | null
}

type InboundPackage = {
  id: string
  kind: 'box' | 'cargo_place'
  number: number
  internal_barcode: string
  request_id: string
  request_display_number: string | null
  warehouse_name: string | null
  intake_status: string
  composition_tracked: boolean
  fully_distributed: boolean
  remaining_qty: number | null
  lines: InboundPackageLine[]
  source_document: SourceDocument
}

export type CatalogInboundPackageProduct = {
  id: string
  name: string
  sku_code: string
  seller_name: string | null
  wb_vendor_code: string | null
  wb_size: string | null
  wb_primary_image_url: string | null
  wb_primary_barcode: string | null
  wb_barcodes: string[]
}

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  products: CatalogInboundPackageProduct[]
}

type PackageCompositionRow = InboundPackageLine & {
  wb_primary_image_url: string | null
  wb_primary_barcode: string | null
  wb_barcodes: string[]
}

function EmptyPanel({ title, hint }: { title: string; hint?: string }) {
  return (
    <Box sx={{ py: 2, color: 'text.secondary' }}>
      <Typography variant="body2">{title}</Typography>
      {hint ? (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      ) : null}
    </Box>
  )
}

function packageTitle(item: InboundPackage): string {
  return `${item.kind === 'box' ? 'Короб' : 'Грузоместо'} № ${item.number}`
}

const sourceDocumentLabels: Record<string, string> = {
  inbound_intake: 'Приёмка',
}

function sourceDocumentTitle(source: SourceDocument): string {
  const label = sourceDocumentLabels[source.kind] ?? 'Документ'
  const number = source.number ?? source.id
  return `${label} ${number.includes('№') ? number : `№ ${number}`}`
}

function sourceDocumentDate(source: SourceDocument): string {
  const value = new Date(source.date)
  return Number.isNaN(value.getTime()) ? '—' : value.toLocaleDateString('ru-RU')
}

async function lookupErrorMessage(response: Response): Promise<string> {
  if (response.status === 404) return 'Короб или грузоместо не найдено'
  if (response.status === 401) return 'Сессия истекла. Войдите заново.'
  if (response.status === 403) return 'Нет доступа к коробам и грузоместам.'
  await readApiErrorMessage(response)
  return 'Не удалось выполнить поиск. Повторите сканирование.'
}

type PackageAccordionProps = {
  item: InboundPackage
  productsById: Map<string, CatalogInboundPackageProduct>
  expanded: boolean
  highlighted: boolean
  onExpandedChange: (packageId: string, expanded: boolean) => void
}

const PackageAccordion = memo(function PackageAccordion({
  item,
  productsById,
  expanded,
  highlighted,
  onExpandedChange,
}: PackageAccordionProps) {
  const compositionRows = useMemo<PackageCompositionRow[]>(
    () =>
      item.lines.map((line) => {
        const product = productsById.get(line.product_id)
        return {
          ...line,
          name: line.name,
          sku_code: line.sku_code,
          seller_name: line.seller_name,
          wb_vendor_code: line.wb_vendor_code,
          wb_size: line.wb_size,
          wb_primary_image_url: product?.wb_primary_image_url ?? null,
          wb_primary_barcode: line.wb_barcode ?? product?.wb_primary_barcode ?? null,
          wb_barcodes: line.wb_barcode ? [line.wb_barcode] : (product?.wb_barcodes ?? []),
        }
      }),
    [item.lines, productsById],
  )
  const completed = item.intake_status === 'done'
  const fullyDistributed = item.kind === 'box' && item.fully_distributed

  return (
    <Accordion
      id={`ff-catalog-inbound-package-${item.id}`}
      expanded={expanded}
      onChange={(_, isExpanded) => onExpandedChange(item.id, isExpanded)}
      disableGutters
      elevation={0}
      data-testid={`ff-catalog-inbound-package-${item.id}`}
      sx={{
        mb: 1,
        overflow: 'hidden',
        border: '1px solid',
        borderColor: 'divider',
        '&::before': { display: 'none' },
        ...(highlighted
          ? {
              bgcolor: 'rgba(46, 125, 50, 0.08)',
              borderLeft: '3px solid',
              borderLeftColor: 'success.main',
            }
          : {}),
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        aria-controls={`ff-catalog-inbound-package-content-${item.id}`}
        id={`ff-catalog-inbound-package-header-${item.id}`}
        sx={{
          px: 2,
          minHeight: 48,
          '& .MuiAccordionSummary-content': { my: 1, minWidth: 0 },
        }}
      >
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={{ xs: 0.25, sm: 2 }}
          sx={{
            minWidth: 0,
            width: '100%',
            pr: 1,
            alignItems: { sm: 'center' },
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
            {packageTitle(item)}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
            {item.internal_barcode}
          </Typography>
          <Stack direction="row" spacing={2} sx={{ minWidth: 0, ml: { sm: 'auto' }, flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary" noWrap>
              {sourceDocumentTitle(item.source_document)} · {sourceDocumentDate(item.source_document)}
            </Typography>
            {item.warehouse_name ? (
              <Typography variant="body2" color="text.secondary" noWrap>
                Склад: {item.warehouse_name}
              </Typography>
            ) : null}
          </Stack>
        </Stack>
      </AccordionSummary>
      <AccordionDetails id={`ff-catalog-inbound-package-content-${item.id}`} sx={{ px: 2, pb: 2, pt: 0 }}>
        {item.kind === 'cargo_place' ? (
          <EmptyPanel
            title={completed ? 'Приёмка завершена' : 'Состав по грузоместу не ведётся'}
            hint={completed ? 'Состав по грузоместу не ведётся' : undefined}
          />
        ) : fullyDistributed || completed ? (
          <EmptyPanel title="Товар из короба уже разложен" hint="Исторический состав здесь не показывается." />
        ) : compositionRows.length === 0 ? (
          <EmptyPanel title="В коробе пока нет товаров" hint="Наполните короб в разделе «Приёмка»." />
        ) : (
          <TableContainer
            sx={{ maxWidth: '100%', overflowX: 'auto' }}
            data-testid={`ff-catalog-inbound-composition-${item.id}`}
          >
            <Table
              size="small"
              sx={{
                minWidth: 1118,
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
                <col style={{ width: 200 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 118 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 64 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 220 }} />
              </colgroup>
              <TableHead>
                <TableRow>
                  <TableCell>Фото</TableCell>
                  <TableCell>Название</TableCell>
                  <TableCell>Артикул продавца</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell>ШК</TableCell>
                  <TableCell>Размер</TableCell>
                  <TableCell>Селлер</TableCell>
                  <TableCell align="right">В коробе</TableCell>
                  <TableCell>Документ прихода</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {compositionRows.map((row) => (
                  <TableRow key={row.product_id} hover data-testid="ff-catalog-inbound-product-row">
                    <TableCell>
                      <ProductPhotoThumb src={row.wb_primary_image_url} alt={row.name} />
                    </TableCell>
                    <TableCell>
                      <Typography
                        component="span"
                        variant="body2"
                        title={row.name}
                        sx={{
                          minWidth: 0,
                          display: '-webkit-box',
                          WebkitBoxOrient: 'vertical',
                          WebkitLineClamp: 2,
                          overflow: 'hidden',
                          lineHeight: 1.25,
                        }}
                      >
                        {row.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                        {row.wb_vendor_code ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                        {row.sku_code}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <ProductBarcodeCell
                        barcode={row.wb_primary_barcode ?? row.wb_barcodes[0] ?? null}
                        wb_size={null}
                        wb_composition={null}
                        testId={`ff-catalog-inbound-barcode-${item.id}-${row.product_id}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {row.wb_size ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                        {row.seller_name ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{row.remaining_qty}</TableCell>
                    <TableCell data-testid={`ff-catalog-inbound-source-${item.id}-${row.product_id}`}>
                      <Typography variant="body2" noWrap title={sourceDocumentTitle(item.source_document)}>
                        {sourceDocumentTitle(item.source_document)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {sourceDocumentDate(item.source_document)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </AccordionDetails>
    </Accordion>
  )
})

export function FfCatalogInboundPackages({ token, authHeaders, products }: Props) {
  const [listLoading, setListLoading] = useState(false)
  const [listLoaded, setListLoaded] = useState(false)
  const [listError, setListError] = useState(false)
  const [listedPackages, setListedPackages] = useState<InboundPackage[]>([])
  const [addressedPackage, setAddressedPackage] = useState<InboundPackage | null>(null)
  const [openPackageId, setOpenPackageId] = useState<string | null>(null)
  const [highlightedPackageId, setHighlightedPackageId] = useState<string | null>(null)
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [scanAnnouncement, setScanAnnouncement] = useState('')
  const requestSequence = useRef(0)
  const scanInputRef = useRef<HTMLInputElement>(null)

  const productsById = useMemo(() => new Map(products.map((product) => [product.id, product])), [products])

  const packages = useMemo(() => {
    if (!addressedPackage) return listedPackages
    const matchingListedPackage = listedPackages.find((item) => item.id === addressedPackage.id)
    if (!matchingListedPackage) return [addressedPackage, ...listedPackages]
    return listedPackages.map((item) => (item.id === addressedPackage.id ? addressedPackage : item))
  }, [addressedPackage, listedPackages])

  const visiblePackages = listLoading ? (addressedPackage ? [addressedPackage] : []) : packages

  const loadList = useCallback(async () => {
    setListLoading(true)
    setListError(false)
    try {
      const response = await fetch(apiUrl('/operations/inbound-packages'), {
        headers: { ...authHeaders(token) },
      })
      if (!response.ok) throw new Error('inbound_packages_load_failed')
      setListedPackages((await response.json()) as InboundPackage[])
      setListLoaded(true)
    } catch {
      setListError(true)
    } finally {
      setListLoading(false)
    }
  }, [authHeaders, token])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const lookup = useCallback(
    async (barcode: string): Promise<void> => {
      const sequence = requestSequence.current + 1
      requestSequence.current = sequence
      setScanError(null)
      setScanAnnouncement('')
      setScanLoading(true)
      try {
        const response = await fetch(
          apiUrl(`/operations/inbound-packages/lookup?barcode=${encodeURIComponent(barcode)}`),
          { headers: { ...authHeaders(token) } },
        )
        if (requestSequence.current !== sequence) return
        if (!response.ok) {
          setScanError(await lookupErrorMessage(response))
          return
        }
        const item = (await response.json()) as InboundPackage
        if (requestSequence.current !== sequence) return
        setAddressedPackage(item)
        setOpenPackageId(item.id)
        setHighlightedPackageId(item.id)
        setScanAnnouncement(`${packageTitle(item)} открыт`)
        window.setTimeout(() => {
          document.getElementById(`ff-catalog-inbound-package-${item.id}`)?.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest',
          })
        }, 0)
      } catch {
        if (requestSequence.current === sequence) {
          setScanError('Нет связи с сервером. Повторите сканирование.')
        }
      } finally {
        if (requestSequence.current === sequence) {
          setScanLoading(false)
          window.setTimeout(() => {
            scanInputRef.current?.focus()
            scanInputRef.current?.select()
          }, 0)
        }
      }
    },
    [authHeaders, token],
  )

  const handleScanKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key !== 'Enter') return
      const barcode = scanValue.trim().toUpperCase()
      if (!barcode) return
      event.preventDefault()
      void lookup(barcode)
    },
    [lookup, scanValue],
  )

  const handlePackageExpandedChange = useCallback((packageId: string, expanded: boolean) => {
    setOpenPackageId(expanded ? packageId : null)
  }, [])

  return (
    <Box data-testid="ff-catalog-inbound-packages">
      <Paper
        variant="outlined"
        sx={{ p: 2, mb: 2, bgcolor: 'action.hover' }}
        data-testid="ff-catalog-inbound-packages-scanner"
      >
        <TextField
          inputRef={scanInputRef}
          fullWidth
          size="small"
          label="Сканер короба или грузоместа"
          value={scanValue}
          onChange={(event) => {
            setScanValue(event.target.value)
            setScanError(null)
          }}
          onKeyDown={handleScanKeyDown}
          placeholder="Сканируйте внутренний ШК"
          error={scanError !== null}
          disabled={scanLoading}
          helperText={scanLoading ? 'Ищем короб…' : 'После скана нужный короб раскроется и подсветится.'}
          slotProps={{
            htmlInput: { 'data-testid': 'ff-catalog-inbound-packages-scan' },
          }}
        />
        <Box
          role="status"
          aria-live="polite"
          sx={{
            position: 'absolute',
            width: 1,
            height: 1,
            p: 0,
            m: -1,
            overflow: 'hidden',
            clip: 'rect(0 0 0 0)',
          }}
        >
          {scanAnnouncement}
        </Box>
        {scanError ? (
          <Alert severity="error" sx={{ mt: 1 }} data-testid="ff-catalog-inbound-packages-lookup-error">
            {scanError}
          </Alert>
        ) : null}
      </Paper>

      {listLoading ? (
        <Stack
          direction="row"
          spacing={1}
          sx={{ p: 2, alignItems: 'center' }}
          data-testid="ff-catalog-inbound-packages-skeleton"
        >
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Загружаем короба и грузоместа…
          </Typography>
        </Stack>
      ) : null}

      {listError ? (
        <Stack spacing={1.5} sx={{ p: 2, alignItems: 'flex-start' }}>
          <Alert severity="error" data-testid="ff-catalog-inbound-packages-error">
            Не удалось загрузить короба и грузоместа
          </Alert>
          <Button variant="contained" onClick={() => void loadList()} data-testid="ff-catalog-inbound-packages-retry">
            Повторить
          </Button>
        </Stack>
      ) : null}

      {listLoaded && !listLoading && !listError && packages.length === 0 ? (
        <EmptyPanel title="Коробов и грузомест пока нет" hint="Создайте короб или грузоместо в разделе «Приёмка»." />
      ) : null}

      {visiblePackages.map((item) => (
        <PackageAccordion
          key={item.id}
          item={item}
          productsById={productsById}
          expanded={openPackageId === item.id}
          highlighted={highlightedPackageId === item.id}
          onExpandedChange={handlePackageExpandedChange}
        />
      ))}
    </Box>
  )
}
