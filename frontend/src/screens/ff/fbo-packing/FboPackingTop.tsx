import { Stack } from '@mui/material'
import { FboPackingProductsTable } from './FboPackingProductsTable'
import { FboPackingScanBar } from './FboPackingScanBar'
import { useFboPacking } from './useFboPacking'
import type { FboPackingDetail } from './fboPackingTypes'

export type FboPackingTopProps = {
  token: string
  authHeaders: HeadersInit
  /** Детальный ответ отгрузки (GET …/marketplace-unload-requests/{id}). */
  detail: FboPackingDetail
  /** Выбранный (текущий) короб отгрузки; скан ШК товара кладёт штуку в него. */
  currentBoxId: string | null
  /** Скан ШК короба: выбор или перенос короба — зона раздела коробов. Отказ — исключением. */
  onBoxBarcodeScanned: (code: string) => Promise<void>
  /** Вызывается после каждого успешного изменения: родитель перечитывает отгрузку. */
  onChanged: () => void
  /** Режим просмотра (после проведения): без скана, печати, выдачи и отвязки КИЗ. */
  disabled?: boolean
}

/**
 * WMS-686: верх вкладки «Упаковка» отгрузки FBO — серая строка скана с галками печати
 * и общая таблица товаров (Нужно / В коробах / ЧЗ). Ниже родитель ставит раздел коробов.
 */
export function FboPackingTop({
  token, authHeaders, detail, currentBoxId, onBoxBarcodeScanned, onChanged, disabled = false,
}: FboPackingTopProps) {
  const controller = useFboPacking({ token, authHeaders, detail, currentBoxId, onBoxBarcodeScanned, onChanged })
  return (
    <Stack spacing={1.5} data-testid="fbo-packing-top">
      <FboPackingScanBar controller={controller} disabled={disabled} />
      <FboPackingProductsTable controller={controller} disabled={disabled} />
    </Stack>
  )
}
