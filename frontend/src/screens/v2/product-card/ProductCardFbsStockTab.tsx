import { useState } from 'react'
import { ErrorNotice } from '../../../ui-kit'
import { FbsStockDialogContainer } from '../../ff/products-fbs/FbsStockDialogContainer'
import type { FbsStockDialogRow } from '../../ff/products-fbs/fbsStockDialogLoader'

type WarehouseRow = { id: string; name: string; code: string; is_operational: boolean }

type Props = {
  productId: string
  productName: string
  productSku: string
  productSize: string | null
  /** Вкладка существует только у товара с продавцом (R3) — id уже проверен вызывающей стороной. */
  sellerId: string
  sellerName: string | null
  token: string
  warehouses: WarehouseRow[]
  canEditBindings: boolean
  /** Нижняя панель карточки, куда порталятся «Отмена»/«Сохранить», пока эта вкладка активна. */
  footerSlotEl: HTMLElement | null
  /** «Сохранить» и «Отмена» закрывают карточку целиком, как окно закрывается сейчас (R12). */
  onCardClose: (changed: boolean) => void
  /** Идёт запись — карточка не даёт переключить вкладку, пока запрос не завершится. */
  onBusyChange: (busy: boolean) => void
}

/**
 * Вкладка «Задать остаток» карточки товара (WMS-490 D6): то же окно
 * «Остаток для FBS», что открывается кнопкой «Задать остаток» и значком в
 * строке каталога, — тот же контейнер с сетью, то же тело, без переделки.
 * Здесь только сборка одного товара в строку окна и место для ошибки
 * загрузки, которая не закрывает карточку (R16) — окно на её месте просто
 * закрывалось бы, а вкладка обязана остаться на месте.
 */
export function ProductCardFbsStockTab({
  productId,
  productName,
  productSku,
  productSize,
  sellerId,
  sellerName,
  token,
  warehouses,
  canEditBindings,
  footerSlotEl,
  onCardClose,
  onBusyChange,
}: Props) {
  const [loadError, setLoadError] = useState<string | null>(null)

  if (loadError) {
    return <ErrorNotice testId="product-card-fbs-stock-error">{loadError}</ErrorNotice>
  }

  const chosen: FbsStockDialogRow[] = [
    { id: productId, name: productName, sku_code: productSku, wb_size: productSize },
  ]

  return (
    <FbsStockDialogContainer
      token={token}
      sellerId={sellerId}
      sellerName={sellerName ?? '—'}
      chosen={chosen}
      warehouses={warehouses}
      canEditBindings={canEditBindings}
      embedded
      footerSlotEl={footerSlotEl}
      onClose={() => onCardClose(true)}
      onLoadError={setLoadError}
      onBusyChange={onBusyChange}
    />
  )
}
