import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { FbsStockDialog } from './FbsStockDialog'
import {
  loadFbsStockDialog,
  toStockDialogProduct,
  type ApiBulkRuleItem,
  type FbsStockDialogData,
  type FbsStockDialogRow,
} from './fbsStockDialogLoader'
import type { CabinetWarehouse, StockBinding } from './fbsStockBlocks'

// Окно «Остаток для FBS» с сетью (WMS-469). Одно на три входа: каталог ФФ,
// экран остатков FBS и кабинет селлера. Здесь — загрузка, сохранение правила,
// добавление связки, смена склада ФФ и приём заказов; само окно про сеть не
// знает и рисует то, что ему дали.
//
// Связка и приём заказов сохраняются сразу и относятся ко всему продавцу;
// «Отмена» их не откатывает. Лимиты выбранных товаров уходят только по
// «Сохранить». Любой отказ или потеря ответа оставляют окно открытым с
// причиной и введённым черновиком (R16, R17).

type WarehouseOption = { id: string; name: string; code?: string; is_operational?: boolean }

/** Технические склады FBS WB и выключенные склады в выбор «Склад ФФ» не попадают. */
export function selectableWmsWarehouses(warehouses: WarehouseOption[]): Array<{ id: string; name: string }> {
  return warehouses
    .filter((one) => one.is_operational !== false)
    .filter((one) => !(one.code ?? '').startsWith('fbs-wb-') && !one.name.startsWith('FBS WB '))
    .map((one) => ({ id: one.id, name: one.name }))
}

type SaveResponse = {
  items?: ApiBulkRuleItem[]
  clamps?: Record<string, { requested_value: number; saved_value: number; limiting_product_id: string; limiting_product_name: string }>
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
  const headers = useCallback(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  )

  const load = useCallback(
    () => loadFbsStockDialog({ headers: headers(), sellerId, chosen }),
    [chosen, headers, sellerId],
  )

  useEffect(() => {
    let alive = true
    load()
      .then((loaded) => {
        if (alive) setData(loaded)
      })
      .catch((e: unknown) => {
        if (!alive) return
        onLoadError(e instanceof Error ? e.message : 'Не удалось открыть настройку остатка')
        onClose()
      })
    return () => {
      alive = false
    }
    // Загружаем один раз на открытие: товары и продавец за время жизни окна не меняются.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** Перечитать серверное состояние после немедленного действия. Черновики окна остаются. */
  const reload = useCallback(async () => {
    setData(await load())
  }, [load])

  function close() {
    onClose()
    if (changedRef.current) onChanged?.()
  }

  async function run(action: () => Promise<void>, failureMessage: string) {
    setBusy(true)
    setActionError(null)
    try {
      await action()
      changedRef.current = true
    } catch (e) {
      setActionError(e instanceof Error ? e.message : failureMessage)
    } finally {
      setBusy(false)
    }
  }

  // Одна ручка на связку целиком: сопоставление и «принимаем заказы». Не
  // переданное поле сервер не меняет, но текущий склад ФФ отправляем всегда —
  // так запрос читается однозначно.
  async function putBinding(
    marketplace: 'wb' | 'ozon',
    externalId: string,
    body: { wms_warehouse_id: string; served: boolean },
  ) {
    const res = await fetch(apiUrl(`/fbs-sellers/${sellerId}/warehouses/${externalId}`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...headers() },
      body: JSON.stringify({ marketplace, ...body }),
    })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    await reload()
  }

  function addBinding(warehouse: CabinetWarehouse, wmsWarehouseId: string) {
    void run(
      () => putBinding(warehouse.marketplace, warehouse.externalId, { wms_warehouse_id: wmsWarehouseId, served: true }),
      'Не удалось добавить склад',
    )
  }

  function changeWmsWarehouse(binding: StockBinding, wmsWarehouseId: string) {
    void run(
      () => putBinding(binding.marketplace, binding.externalId, { wms_warehouse_id: wmsWarehouseId, served: binding.served }),
      'Не удалось сменить склад ФФ',
    )
  }

  function setServed(binding: StockBinding, served: boolean) {
    void run(
      () => putBinding(binding.marketplace, binding.externalId, { wms_warehouse_id: binding.wmsWarehouseId, served }),
      served ? 'Не удалось включить приём заказов' : 'Не удалось отключить приём заказов',
    )
  }

  function save(byBinding: Record<string, { publish: boolean; mode: 'percent' | 'units'; value: number }>) {
    if (!data) return
    void run(async () => {
      const res = await fetch(apiUrl('/products/fbs-rule'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...headers() },
        // PUT /products/fbs-rule ждёт правило вложенным в rule.
        body: JSON.stringify({ product_ids: chosen.map((one) => one.id), rule: { by_binding: byBinding } }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const saved = (await res.json()) as SaveResponse
      const clamps = saved.clamps ?? {}
      changedRef.current = true
      if (Object.keys(clamps).length === 0) {
        close()
        return
      }
      // Свободный остаток изменился между открытием и сохранением, и сервер
      // сохранил меньше запрошенного. Успех есть, но не тот, что на экране:
      // показываем фактически сохранённое и подпись с ограничившим товаром.
      const savedById = new Map((saved.items ?? []).map((one) => [one.product_id, one]))
      setData((current) =>
        current
          ? {
              ...current,
              products: current.products.map((product) => {
                const row = chosen.find((one) => one.id === product.id)
                const item = savedById.get(product.id)
                return row && item ? toStockDialogProduct(row, item) : product
              }),
            }
          : current,
      )
      setServerClamps(
        Object.fromEntries(
          Object.entries(clamps).map(([bindingId, clamp]) => [
            bindingId,
            { free: clamp.saved_value, product: { name: clamp.limiting_product_name } },
          ]),
        ),
      )
    }, 'Не удалось сохранить правило')
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
