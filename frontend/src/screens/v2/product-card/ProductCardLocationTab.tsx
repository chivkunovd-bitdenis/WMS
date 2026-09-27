import { Box } from '@mui/material'
import type { ProductCardLocationWarehouse } from './productCardTypes'

// Заглушка куска D3: вкладку целиком собирает D5 (WMS-490) — то же дерево
// «Карты склада» (`WarehouseMapTree` + `buildRows`), отфильтрованное по этому
// товару, с теми же действиями (перемещение, пересчёт, печать ШК ячейки,
// расформирование палеты). Сигнатура пропсов намеренно совпадает с остальными
// вкладками карточки, чтобы D5 подключил свою реализацию, не трогая
// ProductCardDialog.tsx.
type Props = {
  productId: string
  token: string
  authHeaders: (t: string) => Record<string, string>
  /** Склады, где у товара есть остаток или незавершённая приёмка (из `/products/{id}/card`, D1). */
  locationWarehouses: ProductCardLocationWarehouse[]
  /** Товара с таким id больше нет — вкладка должна уметь сообщить об этом наверх (R16). */
  onNotFound: () => void
  /** Пересчёт на вкладке меняет остаток — карточка должна перечитать шапку и «Движения» (R11). */
  onStockChanged: () => void
}

export function ProductCardLocationTab(_props: Props) {
  return <Box data-testid="product-card-location-tab-placeholder" />
}
