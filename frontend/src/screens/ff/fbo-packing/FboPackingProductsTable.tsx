import { Fragment, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import ArticleOutlined from '@mui/icons-material/ArticleOutlined'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import ErrorOutlineOutlined from '@mui/icons-material/ErrorOutlineOutlined'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { resolveProductPrimaryBarcode } from '../../../types/wbProductCatalog'
import type { FboMarkingCode, FboProductRow } from './fboPackingTypes'
import type { FboPackingController } from './useFboPacking'

export const FBO_CHZ_HINT_TEXT =
  'Не все КИЗ привязаны. Если товар перенесён целым коробом, КИЗ этих единиц не сканировали; привязаны только показанные коды'

/** Служебные символы (GS) в коде не видны и ломают перенос строки. */
function printableCode(code: string): string {
  return code.replace(/[\u0000-\u001f\u007f]/g, '')
}

function MarkingCodesList({ productId, codes, busy, disabled, controller }: {
  productId: string
  codes: FboMarkingCode[]
  busy: boolean
  disabled: boolean
  controller: FboPackingController
}) {
  return (
    <Stack data-testid={`fbo-packing-codes-${productId}`}>
      {codes.map((code, index) => (
        <Stack
          key={code.marking_code_id}
          direction="row"
          spacing={1}
          data-testid={`fbo-packing-code-${code.marking_code_id}`}
          sx={{
            alignItems: 'center',
            py: 0.5,
            borderBottom: index < codes.length - 1 ? 1 : 0,
            borderColor: 'divider',
          }}
        >
          <Box sx={{ minWidth: 0, flex: '0 1 auto' }}>
            <Typography variant="body2" title={printableCode(code.cis_code)} sx={{ wordBreak: 'break-all' }}>
              {printableCode(code.cis_code)}
            </Typography>
            {code.intake_document_number ? (
              <Typography variant="caption" color="text.secondary">
                приёмка №{code.intake_document_number}
              </Typography>
            ) : null}
          </Box>
          <Button
            size="small"
            disabled={busy || disabled}
            onClick={() => void controller.reprintCode(code)}
            data-testid={`fbo-packing-code-reprint-${code.marking_code_id}`}
            sx={{ flexShrink: 0 }}
          >
            Перепечатать
          </Button>
          <Tooltip title="Отвязать код">
            <span>
              <IconButton
                size="small"
                aria-label="Отвязать код"
                disabled={busy || disabled}
                onClick={() => void controller.unbindCode(code)}
                data-testid={`fbo-packing-code-unbind-${code.marking_code_id}`}
              >
                <CloseOutlined fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      ))}
    </Stack>
  )
}

/**
 * Общая таблица товаров упаковки FBO. Колонки и вид — как у прежней таблицы упаковки,
 * плюс «Нужно» (P), «В коробах» (B) и «ЧЗ» «K из P». Данные — из отгрузки и списка кодов.
 */
export function FboPackingProductsTable({ controller, disabled = false }: {
  controller: FboPackingController
  disabled?: boolean
}) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const [instructions, setInstructions] = useState<{ title: string; text: string } | null>(null)

  const toggle = (productId: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(productId)) next.delete(productId)
      else next.add(productId)
      return next
    })

  const renderChz = (row: FboProductRow, k: number) => {
    const showCounter = controller.requiresChz(row.productId) || k > 0
    const incomplete = showCounter && k < row.need
    if (!showCounter) {
      return <Chip size="small" variant="outlined" label="не требуется" data-testid={`fbo-packing-chz-none-${row.productId}`} />
    }
    return (
      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.5 }}>
        <Chip
          size="small"
          color={incomplete ? 'error' : 'default'}
          variant="outlined"
          label={`${k} из ${row.need}`}
          clickable={k > 0}
          onClick={k > 0 ? () => toggle(row.productId) : undefined}
          aria-expanded={k > 0 ? expanded.has(row.productId) : undefined}
          data-testid={`fbo-packing-chz-${row.productId}`}
        />
        {incomplete ? (
          <Tooltip title={FBO_CHZ_HINT_TEXT}>
            <Box
              component="span"
              tabIndex={0}
              role="img"
              aria-label={FBO_CHZ_HINT_TEXT}
              data-testid={`fbo-packing-chz-hint-${row.productId}`}
              sx={{ display: 'inline-flex', color: 'error.main', cursor: 'help' }}
            >
              <ErrorOutlineOutlined fontSize="small" />
            </Box>
          </Tooltip>
        ) : null}
      </Stack>
    )
  }

  return (
    <Stack spacing={1}>
      {controller.codesError ? (
        <Alert severity="warning" data-testid="fbo-packing-codes-error">{controller.codesError}</Alert>
      ) : null}
      <TableContainer component={Paper} variant="outlined" data-testid="ff-packaging-lines-table">
        <Table size="small" sx={{ tableLayout: 'fixed', width: '100%', minWidth: 1100 }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: '22%' }}>Товар</TableCell>
              <TableCell sx={{ width: '9%' }}>Артикул продавца</TableCell>
              <TableCell sx={{ width: '8%' }}>Артикул WB</TableCell>
              <TableCell sx={{ width: '6%' }}>Размер</TableCell>
              <TableCell sx={{ width: '13%' }}>ШК</TableCell>
              <TableCell align="center" sx={{ width: '4%' }}>ТЗ</TableCell>
              <TableCell align="right" sx={{ width: '6%' }}>Нужно</TableCell>
              <TableCell align="right" sx={{ width: '7%' }}>В коробах</TableCell>
              <TableCell sx={{ width: '12%' }}>ЧЗ</TableCell>
              <TableCell align="right" sx={{ width: '12%' }}>Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {controller.rows.map((row) => {
              const meta = controller.metaOf(row)
              const lineId = row.lineIds[0] ?? row.productId
              const barcode = resolveProductPrimaryBarcode(meta) || row.skuCode
              const k = controller.kizCountOf(row)
              const showCounter = controller.requiresChz(row.productId) || k > 0
              const incomplete = showCounter && k < row.need
              const busy = controller.busyProductId === row.productId
              const tz = (row.packagingInstructions ?? meta.packaging_instructions ?? '').trim()
              const codes = controller.codesByProduct.get(row.productId) ?? []
              const message = controller.rowMessages[row.productId]
              return (
                <Fragment key={row.productId}>
                  <TableRow
                    data-testid={incomplete ? 'ff-packaging-line-marking-incomplete' : 'ff-packaging-line'}
                    data-product-id={row.productId}
                  >
                    <TableCell sx={{ overflow: 'hidden' }}>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
                        <ProductPhotoThumb
                          src={meta.wb_primary_image_url}
                          alt={meta.product_name}
                          testId={`ff-packaging-line-photo-${lineId}`}
                        />
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap data-testid="ff-packaging-compact-product-name">
                            {meta.product_name}
                          </Typography>
                        </Box>
                      </Stack>
                    </TableCell>
                    <TableCell sx={{ overflow: 'hidden' }}>
                      <Typography variant="body2" noWrap data-testid={`ff-packaging-line-vendor-code-${lineId}`}>
                        {meta.wb_vendor_code || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ overflow: 'hidden' }}>
                      <Typography variant="body2" noWrap data-testid={`ff-packaging-line-nm-id-${lineId}`}>
                        {meta.wb_nm_id ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ overflow: 'hidden' }}>
                      <Typography variant="body2" noWrap data-testid={`ff-packaging-line-size-${lineId}`}>
                        {meta.wb_size || ''}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ wordBreak: 'break-word' }} data-testid={`ff-packaging-line-barcode-${lineId}`}>
                        {barcode || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title={tz || 'ТЗ не задано'}>
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => setInstructions({ title: `${meta.product_name} · SKU ${meta.sku_code}`, text: tz })}
                            data-testid={`ff-packaging-line-tz-${lineId}`}
                            aria-label={tz ? 'Показать задание на упаковку' : 'Задание на упаковку не задано'}
                          >
                            <ArticleOutlined fontSize="small" color={tz ? 'primary' : 'disabled'} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" data-testid={`fbo-packing-need-${row.productId}`}>{row.need}</Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" data-testid={`fbo-packing-boxed-${row.productId}`}>{row.inBoxes}</Typography>
                    </TableCell>
                    <TableCell>
                      {renderChz(row, k)}
                      {message ? (
                        <Typography
                          variant="caption"
                          color="error"
                          sx={{ display: 'block', mt: 0.5 }}
                          data-testid={`fbo-packing-row-message-${row.productId}`}
                        >
                          {message}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right" sx={{ py: 1 }}>
                      <Stack spacing={0.5} sx={{ alignItems: 'flex-end' }}>
                        <Button
                          variant="contained"
                          size="large"
                          startIcon={<PrintOutlined />}
                          aria-label={`Печать товара ${meta.product_name}`}
                          onClick={() => void controller.printLine(row.productId)}
                          data-testid={`ff-packaging-line-print-${lineId}`}
                          disabled={busy || disabled}
                          sx={{ whiteSpace: 'nowrap' }}
                        >
                          ШК + ЧЗ
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                  {expanded.has(row.productId) && codes.length > 0 ? (
                    <TableRow data-testid={`fbo-packing-codes-row-${row.productId}`}>
                      <TableCell colSpan={10} sx={{ py: 0.5 }}>
                        <MarkingCodesList
                          productId={row.productId}
                          codes={codes}
                          busy={busy}
                          disabled={disabled}
                          controller={controller}
                        />
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              )
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <Dialog
        open={Boolean(instructions)}
        onClose={() => setInstructions(null)}
        maxWidth="xs"
        fullWidth
        data-testid="ff-packaging-instructions-dialog"
      >
        <DialogTitle>Задание на упаковку</DialogTitle>
        <DialogContent>
          {instructions ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              {instructions.title}
            </Typography>
          ) : null}
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }} data-testid="ff-packaging-instructions-dialog-text">
            {instructions?.text.trim() || 'ТЗ не задано'}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInstructions(null)} data-testid="ff-packaging-instructions-dialog-close">
            Закрыть
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
