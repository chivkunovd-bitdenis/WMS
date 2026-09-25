import { Stack, Typography } from '@mui/material'
import { formatStockQty } from '../utils/formatStockQty'

export type ProductStockTotals = {
  /** Остаток — все строки остатка товара в организации (WMS-530 R1). */
  onHand: number
  /** Резерв — брони документов, заказов и ручные направления (R2). */
  reserved: number
  /** Доступно = Остаток − Резерв, может быть меньше нуля (R3). */
  available: number
}

/**
 * Ячейка «Остаток» в каталоге ФФ и в кабинете селлера (WMS-532): три строки
 * «Остаток / Резерв / Доступно» с одними и теми же числами.
 *
 * Строки не обрезаются: если число не помещается рядом с подписью, оно
 * переносится под неё в той же ячейке. Разряды разделены неразрывным пробелом,
 * а минус не отрывается от цифр, поэтому перенос возможен только между
 * подписью и числом.
 */
export function ProductStockLines({
  totals,
  productId,
  testIdPrefix,
  fontSize,
}: {
  totals: ProductStockTotals
  productId: string
  /** Строки получают `<префикс>-on-hand|reserved|available-<id товара>`. */
  testIdPrefix: string
  fontSize?: string
}) {
  const lines = [
    { key: 'on-hand', label: 'Остаток', value: totals.onHand, primary: true },
    { key: 'reserved', label: 'Резерв', value: totals.reserved, primary: false },
    { key: 'available', label: 'Доступно', value: totals.available, primary: false },
  ]
  return (
    <Stack spacing={0.15} sx={{ minWidth: 0, alignItems: 'flex-end' }}>
      {lines.map((line) => {
        const text = `${line.label} ${formatStockQty(line.value)}`
        return (
          <Typography
            key={line.key}
            variant="caption"
            color={line.primary ? undefined : 'text.secondary'}
            data-testid={`${testIdPrefix}-${line.key}-${productId}`}
            title={text}
            sx={{ maxWidth: '100%', textAlign: 'right', ...(fontSize ? { fontSize } : {}) }}
          >
            {text}
          </Typography>
        )
      })}
    </Stack>
  )
}
