import type { ReactNode } from 'react'
import { useState } from 'react'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { IconButton, TableCell, Tooltip, Typography } from '@mui/material'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import { ProductBarcodePrintDialog } from './ProductBarcodePrintDialog'
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
  nameExtra?: ReactNode
}

export function FfProductLineCells({
  meta,
  showPrint = true,
  printTestId = 'ff-product-barcode-print',
  nameExtra,
}: CellsProps) {
  const [printOpen, setPrintOpen] = useState(false)
  const barcode = resolveProductPrimaryBarcode(meta)
  const printable = Boolean(barcode)

  return (
    <>
      <TableCell>
        <ProductPhotoThumb src={meta.wb_primary_image_url} />
      </TableCell>
      <TableCell sx={{ whiteSpace: 'nowrap', pl: 2 }} title={meta.sku_code}>
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
        <Typography variant="body2" sx={{ lineHeight: 1.25 }}>
          {meta.product_name}
        </Typography>
        {nameExtra}
      </TableCell>
      {showPrint ? (
        <TableCell align="center" sx={{ pr: 1 }}>
          <Tooltip
            title={
              printable
                ? 'Печать этикетки 58×40'
                : 'Нет баркода WB — откройте диалог и синхронизируйте карточки'
            }
          >
            <span>
              <IconButton
                size="small"
                aria-label="Печать ШК товара"
                data-testid={printTestId}
                onClick={() => setPrintOpen(true)}
              >
                <PrintOutlined fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <ProductBarcodePrintDialog
            open={printOpen}
            meta={meta}
            onClose={() => setPrintOpen(false)}
          />
        </TableCell>
      ) : null}
    </>
  )
}
