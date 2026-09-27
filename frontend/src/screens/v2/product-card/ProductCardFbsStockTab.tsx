import type { ReactNode } from 'react'
import { Box } from '@mui/material'

// Заглушка куска D3: вкладку целиком собирает D6 (WMS-490) — тело окна
// «Остаток для FBS» (`FbsStockDialogContainer`/`FbsStockDialog`), вынесенное в
// общий компонент и встроенное сюда без переделки (R12). Кнопки
// «Отмена»/«Сохранить» уходят в нижнюю панель окна карточки через
// `onFooterActionsChange` — слот уже подключён в `ProductCardDialog.tsx`.
// Сигнатура пропсов — контракт для D6, чтобы не трогать сам диалог карточки.
type Props = {
  productId: string
  sellerId: string
  sellerName: string
  token: string
  authHeaders: (t: string) => Record<string, string>
  warehouses: { id: string; name: string; code: string; is_operational: boolean }[]
  canEditBindings: boolean
  /** «Сохранить» закрывает карточку целиком, как окно закрывается сейчас (R12). */
  onCardClose: (changed: boolean) => void
  /** Кнопки «Отмена»/«Сохранить» рисуются в нижней панели окна карточки, не во вкладке. */
  onFooterActionsChange: (actions: ReactNode | null) => void
}

export function ProductCardFbsStockTab(_props: Props) {
  return <Box data-testid="product-card-fbs-stock-tab-placeholder" />
}
