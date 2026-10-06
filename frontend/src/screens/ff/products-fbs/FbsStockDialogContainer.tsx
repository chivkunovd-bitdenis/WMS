import { useEffect, useMemo, useRef, useState } from 'react'
import { FbsStockDialog, FbsStockEmbeddedBody, type FbsStockBodyProps, type SavedRule } from './FbsStockDialog'
import {
  toStockDialogProduct,
  type FbsStockDialogData,
  type FbsStockDialogRow,
} from './fbsStockDialogLoader'
import {
  createStockDialogSession,
  type BindingOutcome,
  type BindingRuleBody,
  type StockDialogSession,
} from './fbsStockDialogSession'
import type { CabinetWarehouse, StockBinding } from './fbsStockBlocks'

// Окно «Остаток для FBS» с сетью (WMS-469). Одно на три входа: каталог ФФ,
// экран остатков FBS и кабинет селлера. Здесь — загрузка, сохранение правила,
// добавление связки и смена склада ФФ; само окно про сеть не знает и рисует
// то, что ему дали. Запросы и их исходы — в
// fbsStockDialogSession.ts.
//
// Связка сохраняется сразу и относится ко всему продавцу; «Отмена» её не
// откатывает. Лимиты выбранных товаров уходят только по
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

const STALE_MESSAGE =
  'Состояние связок не удалось перечитать после сбоя — проверьте связь и повторите действие'

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
  session: sessionOverride,
  embedded = false,
  footerSlotEl = null,
  onBusyChange,
  refreshVersion = 0,
  active = true,
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
  /** Что-то сохранено на сервере: правило или связка. */
  onChanged?: () => void
  /** Окно не открылось: правила или привязки не загрузились. */
  onLoadError: (message: string) => void
  /** Подмена сети в тестах. */
  session?: StockDialogSession
  /**
   * WMS-490 D6: тело встроено во вкладку «Задать остаток» карточки товара —
   * без рамки диалога, а провал загрузки не закрывает карточку (`onClose` не
   * вызывается, только `onLoadError`; хозяин вкладки сам показывает
   * `ErrorNotice` и держит карточку открытой, R16).
   */
  embedded?: boolean
  /** Куда порталить «Отмена»/«Сохранить» в embedded-режиме — нижняя панель карточки. */
  footerSlotEl?: HTMLElement | null
  /** Идёт ли запись — embedded-хозяин запрещает переключать вкладки, пока не завершится. */
  onBusyChange?: (busy: boolean) => void
  /** External stock change in an already mounted product card. */
  refreshVersion?: number
  active?: boolean
}) {
  const [data, setData] = useState<FbsStockDialogData | null>(null)
  // Незавершённые запросы. Окно заперто, пока не завершены все: конец одного
  // не должен разблокировать ввод, пока идёт другой (R16, R17).
  const [pending, setPending] = useState(0)
  const busy = pending > 0
  const [actionError, setActionError] = useState<string | null>(null)
  const [saved, setSaved] = useState<SavedRule>()
  const changedRef = useRef(false)
  // Прошлое перечитывание после сбоя не удалось: окно может держать не тот
  // склад, что на сервере. Перед следующим действием читаем заново.
  const staleRef = useRef(false)
  const appliedRefreshVersion = useRef(refreshVersion)
  const writeEpoch = useRef(0)
  const ownSession = useMemo(
    () => createStockDialogSession({ headers: { Authorization: `Bearer ${token}` }, sellerId }),
    [sellerId, token],
  )
  const session = sessionOverride ?? ownSession

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
    setSaved(undefined)
    staleRef.current = false
    session
      .load(chosenRef.current)
      .then((loaded) => {
        if (alive && loaded) setData(loaded)
      })
      .catch((e: unknown) => {
        if (!alive) return
        onLoadError(e instanceof Error ? e.message : 'Не удалось открыть настройку остатка')
        // Окно закрывается на неудачной загрузке (R16 из его собственной
        // истории: нечего показывать, кроме сообщения снаружи). Встроенная
        // вкладка карточки товара — наоборот: карточка не закрывается,
        // сообщение остаётся во вкладке, повтор — переоткрытием вкладки или
        // карточки (WMS-490 R16).
        if (!embedded) onClose()
      })
    return () => {
      alive = false
    }
    // onLoadError/onClose/embedded — обработчики и режим родителя, на них
    // загрузка не завязана.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, chosenKey])

  // A different card tab changed stock. Refresh server facts in place: the
  // form owns touched drafts and must stay mounted while totals are replaced.
  useEffect(() => {
    if (!embedded || !active || busy || !data || refreshVersion === appliedRefreshVersion.current) return
    let alive = true
    const epoch = writeEpoch.current
    void session.reread().then((fresh) => {
      if (!alive || epoch !== writeEpoch.current) return
      if (fresh) {
        setData(fresh)
        appliedRefreshVersion.current = refreshVersion
        setActionError(null)
        staleRef.current = false
      } else {
        setActionError('Не удалось обновить остаток. Повторите открытие вкладки.')
      }
    })
    return () => { alive = false }
  }, [embedded, active, busy, data, refreshVersion, session])

  // Пока идёт запись, хозяин встроенной вкладки не даёт переключиться на
  // другую вкладку карточки — иначе контейнер размонтируется посреди запроса
  // (R16, R17: «конец одного не должен разблокировать ввод, пока идёт другой»
  // относится и к самому факту, что запрос ещё жив).
  useEffect(() => {
    if (embedded) onBusyChange?.(busy)
  }, [embedded, busy, onBusyChange])
  useEffect(() => {
    if (!embedded) return undefined
    return () => onBusyChange?.(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [embedded])

  function close() {
    onClose()
    if (changedRef.current) onChanged?.()
  }

  // Немедленное действие и частичное/неудачное «Сохранить» помечают
  // `changedRef`, но не закрывают окно — `onChanged` из close() выше сработает
  // только когда окно всё-таки закроется через сам контейнер. У встроенной
  // вкладки карточки товара есть и другой путь закрытия — общая «Закрыть»,
  // Escape, фон, — который обходит close() контейнера целиком (ревью WMS-490,
  // F4). Поэтому в embedded-режиме сообщаем наверх сразу в момент записи, не
  // дожидаясь close(); обычное окно эту тонкость не получает — оно закрывается
  // только через контейнер, и раннее сообщение ему не нужно.
  function notifyChanged() {
    changedRef.current = true
    if (embedded) onChanged?.()
  }

  function begin() {
    writeEpoch.current += 1
    setPending((count) => count + 1)
    setActionError(null)
  }
  function end() {
    setPending((count) => count - 1)
  }

  /** Состояние, которому можно верить: после несостоявшегося перечитывания — только свежее. */
  async function trusted(): Promise<FbsStockDialogData | null> {
    if (!staleRef.current) return data
    const fresh = await session.reread()
    if (!fresh) return null
    staleRef.current = false
    setData(fresh)
    return fresh
  }

  /** Немедленное действие со связкой: исход и перечитанное состояние — из сессии. */
  async function immediate(
    binding: Pick<StockBinding, 'id' | 'marketplace' | 'externalId'>,
    body: (current: StockBinding | undefined) => Parameters<StockDialogSession['putBinding']>[2],
  ) {
    begin()
    try {
      const base = await trusted()
      if (!base) {
        setActionError(STALE_MESSAGE)
        return
      }
      const current = base.bindings.find((one) => one.id === binding.id)
      const outcome: BindingOutcome = await session.putBinding(binding.marketplace, binding.externalId, body(current))
      // После отказа состояние на сервере могло измениться (ответ потерян):
      // показываем перечитанное, если оно есть; если и его нет — следующее
      // действие начнётся с перечитывания.
      if (outcome.data) setData(outcome.data)
      else staleRef.current = true
      if (!outcome.ok) setActionError(outcome.message)
      notifyChanged()
    } finally {
      end()
    }
  }

  function addBinding(warehouse: CabinetWarehouse, wmsWarehouseId: string) {
    void immediate(
      { id: '', marketplace: warehouse.marketplace, externalId: warehouse.externalId },
      () => ({ wms_warehouse_id: wmsWarehouseId, served: true }),
    )
  }

  function changeWmsWarehouse(binding: StockBinding, wmsWarehouseId: string) {
    // Только сопоставление: приём заказов не передаём, сервер его не меняет.
    void immediate(binding, () => ({ wms_warehouse_id: wmsWarehouseId }))
  }

  function save(byBinding: Record<string, BindingRuleBody>) {
    if (!data) return
    void (async () => {
      begin()
      try {
        const outcome = await session.saveRule(chosenRef.current.map((one) => one.id), byBinding)
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
            notifyChanged()
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
            setSaved({
              bindingIds: Object.keys(byBinding),
              clamps: Object.fromEntries(
                Object.entries(outcome.clamps).map(([bindingId, clamp]) => [
                  bindingId,
                  { free: clamp.saved_value, product: { name: clamp.limiting_product_name } },
                ]),
              ),
            })
            return
          }
          case 'error':
            // Черновик остаётся в окне; связки и остатки — перечитанные, если
            // перечитать удалось. Правило могло сохраниться до потери ответа —
            // повтор того же запроса состояние не удвоит (R22).
            if (outcome.data) setData(outcome.data)
            setActionError(outcome.message)
            notifyChanged()
            return
        }
      } finally {
        end()
      }
    })()
  }

  if (!data) return null
  // Оба режима собираются из одних и тех же данных и обработчиков — окно и
  // встроенная вкладка карточки товара расходятся только рамкой (WMS-490 D6,
  // R12: «в точности то же самое»).
  const bodyProps: FbsStockBodyProps = {
    sellerName,
    products: data.products,
    bindings: data.bindings,
    cabinets: data.cabinets,
    wmsWarehouses: selectableWmsWarehouses(warehouses),
    canEditBindings,
    busy,
    onClose: close,
    onSave: save,
    onAddBinding: canEditBindings ? addBinding : undefined,
    onChangeWmsWarehouse: canEditBindings ? changeWmsWarehouse : undefined,
    actionError,
    wbWarehousesError: data.wbWarehousesError,
    ozonWarehousesError: data.ozonWarehousesError,
    saved,
  }
  if (embedded) {
    return <FbsStockEmbeddedBody {...bodyProps} footerSlotEl={footerSlotEl} />
  }
  return <FbsStockDialog open {...bodyProps} />
}
