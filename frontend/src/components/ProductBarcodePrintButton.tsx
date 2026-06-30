import { useState } from 'react'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { IconButton, Tooltip } from '@mui/material'
import { ProductBarcodePrintDialog } from './ProductBarcodePrintDialog'
import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'

type Props = {
  meta: ProductLineDisplayMeta
  testId?: string
  /** Для товаров с ЧЗ — открыть полный конструктор вместо простого 58×40. */
  onMarkingPrint?: () => void
}

export function ProductBarcodePrintButton({
  meta,
  testId = 'ff-product-barcode-print',
  onMarkingPrint,
}: Props) {
  const [printOpen, setPrintOpen] = useState(false)
  const printable = Boolean(resolveProductPrimaryBarcode(meta))

  const handleClick = () => {
    if (onMarkingPrint) {
      onMarkingPrint()
      return
    }
    setPrintOpen(true)
  }

  return (
    <>
      <Tooltip
        title={
          onMarkingPrint
            ? 'Печать ЧЗ и ШК ВБ'
            : printable
              ? 'Печать этикетки 58×40'
              : 'Нет баркода WB — откройте диалог и синхронизируйте карточки'
        }
      >
        <span>
          <IconButton
            size="small"
            aria-label="Печать ШК товара"
            data-testid={testId}
            onClick={handleClick}
          >
            <PrintOutlined fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      {onMarkingPrint ? null : (
        <ProductBarcodePrintDialog
          open={printOpen}
          meta={meta}
          onClose={() => setPrintOpen(false)}
        />
      )}
    </>
  )
}
