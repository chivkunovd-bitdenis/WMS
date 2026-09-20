import { useEffect, useMemo, useRef, useState } from 'react'
import { FbsStockDialog } from './FbsStockDialog'
import {
  toStockDialogProduct,
  type FbsStockDialogData,
  type FbsStockDialogRow,
} from './fbsStockDialogLoader'
import { createStockDialogSession, type BindingOutcome, type BindingRuleBody } from './fbsStockDialogSession'
import type { CabinetWarehouse, StockBinding } from './fbsStockBlocks'

// Окно «Остаток для FBS» с сетью (WMS-469). Одно на три входа: каталог ФФ,
// экран остатков FBS и кабинет селлера. Здесь — загрузка, сохранение правила,
// добавление связки, смена склада ФФ и приём заказов; само окно про сеть не
// знает и рисует то, что ему дали. Запросы и их исходы — в
// fbsStockDialogSession.ts.
//
// Связка и приём заказов сохраняются сразу и относятся ко всему продавцу;
// «Отмена» их не откатывает. Лимиты выбранных товаров уходят только по
// «Сохранить» и только для изменённых блоков. Любой отказ или потеря ответа
// оставляют окно открытым с причиной и введённым черновиком, а состояние
// связок перечитывается с сервера (R16, R17).

type WarehouseOption = { id: string; name: string; code?: string; is_operational?: boolean }

/** Технические склады FBS WB и выключенные склады в выбор «Склад ФФ» не попадают. */
export function selectableWmsWarehouses(warehouses: WarehouseOption[]): Array<{ id: string; name: string }> {
  return warehouses
    .filter((one) => one.is_operational !== false)
    .filter((one) => !(one.code ?? '').startsWith('fbs-wb-') && !one.name.startsWith('FBS WB '))
    .map((one) => ({ id: one.id, name: one.name }))
}

export function FbsStockDialogContainer({
  token,
  sellerId,
  sellerName,
  chosen,
  warehouses,
  canEditBindings,
  onClose,
  onChanged,
  onLoadError,
}: {
  token: string
  sellerId: string
  sellerName: string
  /** Товары одного продавца, для которых открывается окно. */
  chosen: FbsStockDialogRow[]
  /** Физические склады ФФ (сырой список /warehouses). */
  warehouses: WarehouseOption[]
  /** Администратор ФФ — да; кабинет селлера — нет (D4). */
  canEditBindings: boolean
  onClose: () => void
  /** Что-то сохранено на сервере: правило, связка или приём заказов. */
  onChanged?: () => void
  /** Окно не открылось: правила или привязки не загрузились. */
  onLoadError: (message: string) => void
}) {
  const [data, setData] = useState<FbsStockDialogData | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [serverClamps, setServerClamps] = useState<Record<string, { free: number; product: { name: string } }>>()
  const changedRef = useRef(false)
  const session = useMemo(
    () => createStockDialogSession({ headers: { Authorization: `Bearer ${token}` }, sellerId }),
    [sellerId, token],
  )

  // Новый набор товаров — новая загрузка. Пока идёт первая, каталог ещё
  // доступен, и выбор могут поменять: ответ прежней загрузки отбрасывается,
  // окно показывает и сохраняет только текущий выбор.
  const chosenKey = chosen.map((one) => one.id).join('|')
  const chosenRef = useRef(chosen)
  chosenRef.current = chosen
  useEffect(() => {
    let alive = true
    setData(null)
    setActionError(null)
    setServerClamps(undefined)
    session
      .load(chosenRef.current)
      .then((loaded) => {
        if (alive && loaded) setData(loaded)
      })
      .catch((e: unknown) => {
        if (!alive) return
        onLoadError(e instanceof Error ? e.message : 'Не удалось открыть настройку остатка')
        onClose()
      })
    return () => {
      alive = false
    }
    // onLoadError/onClose — обработчики родителя, на них загрузка не завязана.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, chosenKey])

  function close() {
    onClose()
    if (changedRef.current) onChanged?.()
  }

  /** Немедленное действие со связкой: исход и перечитанное состояние — из сессии. */
  async function immediate(action: () => Promise<BindingOutcome>) {
    setBusy(true)
    setActionError(null)
    const outcome = await action()
    // После отказа состояние на сервере могло измениться (ответ потерян):
    // показываем перечитанное, если оно есть, и не считаем окно нетронутым.
    if (outcome.data) setData(outcome.data)
    if (!outcome.ok) setActionError(outcome.message)
    changedRef.current = true
    setBusy(false)
  }

  function addBinding(warehouse: CabinetWarehouse, wmsWarehouseId: string) {
    void immediate(() =>
      session.putBinding(warehouse.marketplace, warehouse.externalId, { wms_warehouse_id: wmsWarehouseId, served: true }),
    )
  }

  function changeWmsWarehouse(binding: StockBinding, wmsWarehouseId: string) {
    void immediate(() =>
      session.putBinding(binding.marketplace, binding.externalId, { wms_warehouse_id: wmsWarehouseId, served: binding.served }),
    )
  }

  function setServed(binding: StockBinding, served: boolean) {
    void immediate(() =>
      session.putBinding(binding.marketplace, binding.externalId, { wms_warehouse_id: binding.wmsWarehouseId, served }),
    )
  }

  function save(byBinding: Record<string, BindingRuleBody>) {
    if (!data) return
    void (async () => {
      setBusy(true)
      setActionError(null)
      const outcome = await session.saveRule(chosenRef.current.map((one) => one.id), byBinding)
      setBusy(false)
      switch (outcome.kind) {
        case 'nothing':
          // Изменённых блоков нет: серверу нечего сохранять, запрос не уходил.
          close()
          return
        case 'saved':
          changedRef.current = true
          close()
          return
        case 'clamped': {
          // Свободный остаток изменился между открытием и сохранением, и сервер
          // сохранил меньше запрошенного. Успех есть, но не тот, что на экране:
          // показываем фактически сохранённое и подпись с ограничившим товаром.
          changedRef.current = true
          const savedById = new Map(outcome.items.map((one) => [one.product_id, one]))
          setData((current) =>
            current
              ? {
                  ...current,
                  products: current.products.map((product) => {
                    const row = chosenRef.current.find((one) => one.id === product.id)
                    const item = savedById.get(product.id)
                    return row && item ? toStockDialogProduct(row, item) : product
                  }),
                }
              : current,
          )
          setServerClamps(
            Object.fromEntries(
              Object.entries(outcome.clamps).map(([bindingId, clamp]) => [
                bindingId,
                { free: clamp.saved_value, product: { name: clamp.limiting_product_name } },
              ]),
            ),
          )
          return
        }
        case 'error':
          // Черновик остаётся в окне; связки и остатки — перечитанные, если
          // перечитать удалось. Правило могло сохраниться до потери ответа —
          // повтор того же запроса состояние не удвоит (R22).
          if (outcome.data) setData(outcome.data)
          setActionError(outcome.message)
          changedRef.current = true
          return
      }
    })()
  }

  if (!data) return null
  return (
    <FbsStockDialog
      open
      sellerName={sellerName}
      products={data.products}
      bindings={data.bindings}
      cabinets={data.cabinets}
      wmsWarehouses={selectableWmsWarehouses(warehouses)}
      canEditBindings={canEditBindings}
      busy={busy}
      onClose={close}
      onSave={save}
      onAddBinding={canEditBindings ? addBinding : undefined}
      onChangeWmsWarehouse={canEditBindings ? changeWmsWarehouse : undefined}
      onServedChange={canEditBindings ? setServed : undefined}
      actionError={actionError}
      wbWarehousesError={data.wbWarehousesError}
      ozonWarehousesError={data.ozonWarehousesError}
      serverClamps={serverClamps}
    />
  )
}
