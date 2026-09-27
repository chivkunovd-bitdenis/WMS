import { Box } from '@mui/material'

// Заглушка куска D3: вкладку целиком собирает D4 (WMS-490) — таблица
// движений из той же серверной функции, что отчёт «Остатки и движения»
// (WMS-531), догрузка страниц, пустое состояние и ошибка. Сигнатура пропсов
// намеренно совпадает с остальными вкладками карточки, чтобы D4 подключил
// свою реализацию, не трогая ProductCardDialog.tsx.
type Props = {
  productId: string
  token: string
  authHeaders: (t: string) => Record<string, string>
  /** Товара с таким id больше нет — вкладка должна уметь сообщить об этом наверх (R16). */
  onNotFound: () => void
  /** Открыть документ приёмки по ссылке в строке движения — как у отчёта «Остатки и движения». */
  onOpenInbound?: (id: string) => void
}

export function ProductCardMovementsTab(_props: Props) {
  return <Box data-testid="product-card-movements-tab-placeholder" />
}
