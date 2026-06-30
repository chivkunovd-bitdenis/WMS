import type { ReactNode } from 'react'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { IconButton, TableCell, Tooltip, Typography } from '@mui/material'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import { ProductBarcodePrintButton } from './ProductBarcodePrintButton'
import {
  resolveProductPrimaryBarcode,
  type ProductLineDisplayMeta,
} from '../types/wbProductCatalog'
import { ProductBarcodeCell } from './ProductBarcodeCell'

type HeadProps = {
  showPrint?: boolean
  nameLabel?: string
}

export function FfProductTableHeadCells({ showPrint = true, nameLabel = 'Наименование' }: HeadProps) {
  return (
    <>
      <TableCell sx={{ width: 56 }}>Фото</TableCell>
      <TableCell sx={{ width: 190, pl: 2 }}>Артикул</TableCell>
      <TableCell sx={{ width: 220 }}>ШК</TableCell>
      <TableCell sx={{ width: 140 }}>Артикул продавца</TableCell>
      <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
      <TableCell sx={{ pl: 2, minWidth: 180 }}>{nameLabel}</TableCell>
      {showPrint ? (
        <TableCell align="center" sx={{ width: 56, pr: 1 }} />
      ) : null}
    </>
  )
}

type CellsProps = {
  meta: ProductLineDisplayMeta
  showPrint?: boolean
  printTestId?: string
  /** Префикс data-testid для фото/sku/названия в операционных таблицах. */
  lineTestIdPrefix?: string
  /** Если задан — иконка печати вызывает callback вместо ProductBarcodePrintDialog. */
  onPrintClick?: () => void
  nameExtra?: ReactNode
}

export function FfProductLineCells({
  meta,
  showPrint = true,
  printTestId = 'ff-product-barcode-print',
  lineTestIdPrefix,
  onPrintClick,
  nameExtra,
}: CellsProps) {
  const barcode = resolveProductPrimaryBarcode(meta)

  return (
    <>
      <TableCell>
        <ProductPhotoThumb
          src={meta.wb_primary_image_url}
          alt={meta.product_name}
          testId={lineTestIdPrefix ? `${lineTestIdPrefix}-photo` : undefined}
        />
      </TableCell>
      <TableCell
        sx={{ whiteSpace: 'nowrap', pl: 2 }}
        title={meta.sku_code}
        data-testid={lineTestIdPrefix ? `${lineTestIdPrefix}-sku` : undefined}
      >
        {meta.sku_code}
      </TableCell>
      <TableCell sx={{ maxWidth: 220 }}>
        <ProductBarcodeCell
          barcode={barcode}
          wb_size={meta.wb_size}
          wb_composition={meta.wb_composition}
          testId="ff-product-line-barcode"
        />
      </TableCell>
      <TableCell
        sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
        title={meta.wb_vendor_code ?? '—'}
      >
        {meta.wb_vendor_code ?? '—'}
      </TableCell>
      <TableCell sx={{ pr: 2 }}>{meta.wb_nm_id ?? '—'}</TableCell>
      <TableCell
        sx={{
          pl: 2,
          minWidth: 180,
          whiteSpace: 'normal',
          wordBreak: 'break-word',
          overflow: 'hidden',
        }}
      >
        <Typography
          variant="body2"
          sx={{ lineHeight: 1.25 }}
          data-testid={lineTestIdPrefix ? `${lineTestIdPrefix}-name` : undefined}
        >
          {meta.product_name}
        </Typography>
        {nameExtra}
      </TableCell>
      {showPrint ? (
        <TableCell align="center" sx={{ pr: 1 }}>
          {onPrintClick ? (
            <Tooltip title="Печать этикеток">
              <span>
                <IconButton
                  size="small"
                  aria-label="Печать"
                  data-testid={printTestId}
                  onClick={onPrintClick}
                >
                  <PrintOutlined fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          ) : (
            <ProductBarcodePrintButton meta={meta} testId={printTestId} />
          )}
        </TableCell>
      ) : null}
    </>
  )
}
