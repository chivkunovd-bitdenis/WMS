import { useEffect, useRef, useState } from 'react'
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
  /**
   * Что-то уже записано на сервере (связка, приём заказов, частично или
   * полностью сохранённый лимит) — независимо от того, как в итоге закрылась
   * карточка (WMS-490, ревью №1, F4). Не путать с onCardClose: то — только
   * про «Отмена»/«Сохранить» этой вкладки, это — про сам факт записи.
   */
  onChanged: () => void
  /** Растёт при каждом изменении, которое видно другим вкладкам (пересчёт, сохранение FBS) — контракт карточки, F1. */
  stockVersion: number
  /** Вкладка сейчас видна оператору — контракт карточки, F1; здесь используется для повтора после сбоя (F2). */
  active: boolean
  /** Есть ли у вкладки нерешённая ошибка загрузки — карточка должна вернуть общую «Закрыть» вместо пропавших кнопок (F2). */
  onErrorChange: (hasError: boolean) => void
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
  onChanged,
  stockVersion,
  active,
  onErrorChange,
}: Props) {
  const [loadError, setLoadError] = useState<string | null>(null)
  const [externalRefreshVersion, setExternalRefreshVersion] = useState(0)
  const seenStockVersion = useRef(stockVersion)
  const ownVersionBumps = useRef(0)

  useEffect(() => {
    const changes = stockVersion - seenStockVersion.current
    seenStockVersion.current = stockVersion
    if (changes > ownVersionBumps.current) {
      setExternalRefreshVersion((version) => version + 1)
    }
    ownVersionBumps.current = 0
  }, [stockVersion])

  // Карточка узнаёт о нерешённой ошибке, чтобы вернуть «Закрыть» в нижнюю
  // панель вместо пропавших кнопок этой вкладки (ревью №1, F2).
  useEffect(() => {
    onErrorChange(loadError !== null)
    // onErrorChange — обработчик родителя, на него эффект не завязан.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadError])

  // Повторная активация вкладки после сбоя загрузки повторяет запрос — как и
  // переоткрытие всей карточки (R16). Пока вкладка не переоткрывалась,
  // ошибка остаётся на месте: реагируем только на переход в активную, а не
  // на каждый рендер с уже активной вкладкой.
  useEffect(() => {
    if (active && loadError) setLoadError(null)
    // loadError читается в момент срабатывания; лишний повтор при его
    // собственном изменении не нужен — только при активации.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

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
      onChanged={() => {
        ownVersionBumps.current += 1
        onChanged()
      }}
      onLoadError={setLoadError}
      onBusyChange={onBusyChange}
      refreshVersion={externalRefreshVersion}
      active={active}
    />
  )
}
