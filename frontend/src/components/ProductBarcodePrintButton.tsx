import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { CircularProgress, IconButton, Tooltip } from '@mui/material'
import { useState } from 'react'
import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { useFfProductMarkingPrintContextOptional } from './FfProductMarkingPrintProvider'

type Props = {
  meta: ProductLineDisplayMeta
  testId?: string
  productId?: string
  /** Базовое кол-во товара (принято / к упаковке), как qty_need_pack в отгрузке. */
  qtyNeedPack?: number
  printSource?: 'catalog' | 'packaging'
  requiresHonestSign?: boolean
  markingAvailable?: number
  /** Явный callback (упаковка / ЧЗ-инвентарь с готовыми остатками). */
  onMarkingPrint?: () => void
}

export function ProductBarcodePrintButton({
  meta,
  testId = 'ff-product-barcode-print',
  productId,
  qtyNeedPack,
  printSource,
  requiresHonestSign,
  markingAvailable,
  onMarkingPrint,
}: Props) {
  const [busy, setBusy] = useState(false)
  const ffPrint = useFfProductMarkingPrintContextOptional()
  const printable = Boolean(resolveProductPrimaryBarcode(meta))
  const unifiedPrint = Boolean(productId && !onMarkingPrint && ffPrint)

  const handleClick = () => {
    if (onMarkingPrint) {
      onMarkingPrint()
      return
    }
    if (!productId || !ffPrint) {
      return
    }
    setBusy(true)
    void ffPrint
      .openCatalogProductPrint({
        productId,
        meta,
        qtyNeedPack,
        source: printSource,
        requiresHonestSign,
        markingAvailable,
      })
      .finally(() => {
        setBusy(false)
      })
  }

  const tooltip = onMarkingPrint || unifiedPrint
    ? 'Печать ЧЗ и ШК ВБ'
    : printable
      ? 'Печать этикетки 58×40'
      : 'Нет баркода WB — синхронизируйте карточки'

  if (!onMarkingPrint && !unifiedPrint) {
    return null
  }

  return (
    <Tooltip title={tooltip}>
      <span>
        <IconButton
          size="small"
          aria-label="Печать ШК товара"
          data-testid={testId}
          disabled={busy}
          onClick={handleClick}
        >
          {busy ? <CircularProgress size={18} /> : <PrintOutlined fontSize="small" />}
        </IconButton>
      </span>
    </Tooltip>
  )
}
