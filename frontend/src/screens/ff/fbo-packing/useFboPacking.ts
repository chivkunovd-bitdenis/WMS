import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useWbProductCatalog } from '../../../hooks/useWbProductCatalog'
import { resolveProductBarcodeOptions, type ProductLineDisplayMeta } from '../../../types/wbProductCatalog'
import { printShipmentPackagingSheet } from '../../../utils/printShipmentPackagingSheet'
import { randomId } from '../../../utils/randomId'
import { formatHumanDocumentNumber } from '../documentDisplay'
import {
  FboPackingApiError,
  deleteMarkingCode,
  issueMarkingCodes,
  listMarkingCodes,
  scanMarkingCode,
  scanProductIntoBox,
  type FboPackingApiContext,
} from './fboPackingApi'
import {
  loadFboPackingPrintPreferences,
  saveFboPackingPrintPreferences,
  type FboPackingPrintPreferences,
} from './fboPackingPrefs'
import {
  firstPrintKey,
  printMarkingCodeLabel,
  printMarkingCodes,
  printProductBarcodeLabels,
  productBarcodeForMarketplace,
  productLabelData,
  reprintKey,
} from './fboPackingPrint'
import { buildProductRows, classifyScan, printTargetOf, type FboProductCodes } from './fboPackingScan'
import type { FboMarkingCode, FboMarkingIssueResult, FboPackingDetail, FboProductRow } from './fboPackingTypes'

export type UseFboPackingInput = {
  token: string
  authHeaders: HeadersInit
  detail: FboPackingDetail
  currentBoxId: string | null
  onBoxBarcodeScanned: (code: string) => Promise<void>
  onChanged: () => void
}

type CatalogMarkingFlag = { requires_honest_sign?: boolean }

export const NO_CURRENT_BOX_MESSAGE = 'Сначала отсканируйте или создайте короб'
export const KIZ_ALREADY_LINKED_MESSAGE = 'Этот КИЗ уже привязан к товару'

/**
 * Скан товара с неизвестным исходом: ответ на добавление штуки или на выдачу ЧЗ потерялся даже после
 * автоматического повтора. Операция живёт до первого определённого ответа сервера (2xx или 4xx): ручной
 * повтор того же кода в тот же короб идёт с прежними ключами, поэтому штука и код ЧЗ не задваиваются.
 */
type PendingScan = {
  productId: string | null
  mutationId: string
  issueMutationId: string | null
  unresolved: boolean
}

function isOutcomeUnknown(cause: unknown): boolean {
  return cause instanceof FboPackingApiError && cause.outcomeUnknown
}

function errorText(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback
}

/**
 * Ответ мог потеряться (обрыв связи, 5xx): запрос один раз повторяется автоматически теми же
 * данными и тем же mutation_id, сервер вернёт результат первой попытки, а не выполнит операцию заново.
 * Отказ сервера (4xx) не повторяется.
 */
async function retryOnceIfOutcomeUnknown<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call()
  } catch (cause) {
    if (cause instanceof FboPackingApiError && cause.outcomeUnknown) return call()
    throw cause
  }
}

/** R32: «Выдано N из M: в пуле не хватает КИЗ»; без нехватки сообщения нет. */
function shortageNotice(issued: FboMarkingIssueResult): string | null {
  const shortage = issued.shortage ?? 0
  if (shortage <= 0) return null
  return `Выдано ${issued.items.length} из ${issued.items.length + shortage}: в пуле не хватает КИЗ`
}

/**
 * Состояние и действия верха упаковки FBO: коды ЧЗ отгрузки, разбор скана,
 * печать через WMS Print. Числа таблицы вычисляются из данных отгрузки и списка кодов.
 */
export function useFboPacking(input: UseFboPackingInput) {
  const { token, detail } = input
  const { catalogById, getDisplayMeta } = useWbProductCatalog(token)
  const [codes, setCodes] = useState<FboMarkingCode[]>([])
  const [codesLoaded, setCodesLoaded] = useState(false)
  const [codesError, setCodesError] = useState<string | null>(null)
  const [prefs, setPrefsState] = useState<FboPackingPrintPreferences>(() => loadFboPackingPrintPreferences(token))
  const [busyProductId, setBusyProductId] = useState<string | null>(null)
  const [rowMessages, setRowMessages] = useState<Record<string, string>>({})
  // Выданные коды, которые не ушли в печать: повтор печатает ровно их, новые не выдаются.
  const [unprinted, setUnprinted] = useState<Record<string, FboMarkingCode[]>>({})

  const rows = useMemo(() => buildProductRows(detail), [detail])

  const codesByProduct = useMemo(() => {
    const grouped = new Map<string, FboMarkingCode[]>()
    for (const code of codes) {
      const list = grouped.get(code.product_id)
      if (list) list.push(code)
      else grouped.set(code.product_id, [code])
    }
    return grouped
  }, [codes])

  const metaOf = useCallback(
    (row: FboProductRow): ProductLineDisplayMeta =>
      getDisplayMeta(row.productId, { sku_code: row.skuCode, product_name: row.productName }),
    [getDisplayMeta],
  )

  const productCodes = useMemo<FboProductCodes>(() => {
    const map: FboProductCodes = new Map()
    for (const row of rows) {
      const meta = metaOf(row)
      const list = [row.skuCode, meta.sku_code, ...resolveProductBarcodeOptions(meta).map((option) => option.barcode)]
      map.set(row.productId, list.filter((code) => code.trim().length > 0))
    }
    return map
  }, [rows, metaOf])

  /** K: число кодов товара в отгрузке; пока список не загружен — число из данных отгрузки. */
  const kizCountOf = useCallback(
    (row: FboProductRow): number => (codesLoaded ? (codesByProduct.get(row.productId)?.length ?? 0) : row.kizCount),
    [codesLoaded, codesByProduct],
  )

  /** Включён ли у товара Честный знак: строка отгрузки, иначе каталог, иначе есть ли уже коды. */
  const requiresChz = useCallback(
    (productId: string): boolean => {
      const row = rows.find((item) => item.productId === productId)
      if (row?.requiresHonestSign !== undefined) return row.requiresHonestSign
      const catalog = catalogById.get(productId) as unknown as CatalogMarkingFlag | undefined
      if (catalog?.requires_honest_sign !== undefined) return catalog.requires_honest_sign
      return (codesByProduct.get(productId)?.length ?? 0) > 0
    },
    [rows, catalogById, codesByProduct],
  )

  // Свежие значения для обработчиков скана: очередь сканера зовёт их позже рендера.
  const latest = useRef({ ...input, prefs, rows, productCodes, codesByProduct, requiresChz, unprinted, kizCountOf })
  useLayoutEffect(() => {
    latest.current = { ...input, prefs, rows, productCodes, codesByProduct, requiresChz, unprinted, kizCountOf }
  })
  const lastProductRef = useRef<string | null>(null)
  const issueMutationRef = useRef(new Map<string, string>())
  const loadSequenceRef = useRef(0)
  const lineBarcodeKeyRef = useRef(new Map<string, string>())
  // Сканы с неизвестным исходом: ключ — короб и исходный код.
  const pendingScansRef = useRef(new Map<string, PendingScan>())

  const apiContext = useCallback(
    (): FboPackingApiContext => ({ requestId: latest.current.detail.id, headers: latest.current.authHeaders }),
    [],
  )

  const reloadCodes = useCallback(async (): Promise<void> => {
    const sequence = (loadSequenceRef.current += 1)
    try {
      const next = await listMarkingCodes(apiContext())
      if (sequence !== loadSequenceRef.current) return
      setCodes(next)
      setCodesLoaded(true)
      setCodesError(null)
    } catch (cause) {
      if (sequence !== loadSequenceRef.current) return
      setCodesError(errorText(cause, 'Не удалось загрузить коды ЧЗ отгрузки.'))
    }
  }, [apiContext])

  // Коды читаются при открытии и когда у отгрузки меняются числа (подбор может отвязать коды).
  // Подпись из чисел, а не сам объект: родитель может отдавать новый объект на каждый рендер.
  const dataSignature = `${detail.id}|${detail.status}|${rows
    .map((row) => `${row.productId}:${row.need}:${row.picked}:${row.inBoxes}`)
    .join(',')}`
  useEffect(() => {
    void reloadCodes()
  }, [dataSignature, reloadCodes])

  const setPrefs = useCallback((next: FboPackingPrintPreferences) => {
    setPrefsState(next)
    saveFboPackingPrintPreferences(latest.current.token, next)
  }, [])

  const setRowMessage = useCallback((productId: string, message: string | null) => {
    setRowMessages((current) => {
      if (message === null) {
        if (!(productId in current)) return current
        const { [productId]: _removed, ...rest } = current
        void _removed
        return rest
      }
      return { ...current, [productId]: message }
    })
  }, [])

  const setUnprintedFor = useCallback((productId: string, list: FboMarkingCode[]) => {
    setUnprinted((current) => {
      if (list.length === 0) {
        if (!(productId in current)) return current
        const { [productId]: _removed, ...rest } = current
        void _removed
        return rest
      }
      return { ...current, [productId]: list }
    })
  }, [])

  /**
   * Печать выданных кодов по очереди стабильным ключом первой печати. Невышедшие коды запоминаются:
   * повтор печатает ровно их, новые не выдаются.
   */
  const printCodes = useCallback(
    async (productId: string, list: FboMarkingCode[]): Promise<void> => {
      const outcome = await printMarkingCodes(list, latest.current.token, firstPrintKey)
      setUnprintedFor(productId, outcome.unprinted)
      if (outcome.error) {
        throw new Error(`Коды выданы и привязаны, но печать не удалась: ${outcome.error.message}`)
      }
    },
    [setUnprintedFor],
  )

  /**
   * Выдача свободных кодов товара из пула. Кнопка «ШК + ЧЗ» хранит ключ операции до
   * успешного ответа: после потери ответа повтор вернёт те же коды. Скан штуки приносит свой ключ
   * (scanMutationId): он хранится в незавершённом скане, а внутри одной выдачи при потере ответа
   * запрос один раз повторяется автоматически с тем же ключом.
   */
  const issueCodes = useCallback(
    async (
      productId: string,
      quantity: number | undefined,
      reuseKey = true,
      scanMutationId?: string,
    ): Promise<FboMarkingIssueResult> => {
      const mutationKey = `${productId}:${quantity ?? 'all'}`
      const storeKey = reuseKey && scanMutationId === undefined
      const mutationId = scanMutationId ?? (storeKey ? issueMutationRef.current.get(mutationKey) : undefined) ?? randomId()
      if (storeKey) issueMutationRef.current.set(mutationKey, mutationId)
      let issued: FboMarkingIssueResult
      try {
        const request = () => issueMarkingCodes(apiContext(), { productId, quantity, mutationId })
        issued = await (reuseKey ? request() : retryOnceIfOutcomeUnknown(request))
      } catch (cause) {
        // Потерянный ответ: ключ остаётся, повтор вернёт те же коды. Отказ сервера снимает ключ.
        if (storeKey && !isOutcomeUnknown(cause)) issueMutationRef.current.delete(mutationKey)
        throw cause
      }
      if (storeKey) issueMutationRef.current.delete(mutationKey)
      await reloadCodes()
      latest.current.onChanged()
      return issued
    },
    [apiContext, reloadCodes],
  )

  /** Невышедшие коды товара: печатаются теми же ключами, новые коды не выдаются. */
  const flushUnprinted = useCallback(
    async (productId: string): Promise<boolean> => {
      const pending = latest.current.unprinted[productId]
      if (!pending || pending.length === 0) return false
      await printCodes(productId, pending)
      return true
    },
    [printCodes],
  )

  /**
   * Скан штуки с «Печатать ЧЗ»: один код на штуку (quantity=1), привязать и напечатать.
   * Ключ выдачи принадлежит скану и переживает потерянный ответ.
   */
  const issueOneAndPrint = useCallback(
    async (productId: string, scan: PendingScan): Promise<void> => {
      await flushUnprinted(productId)
      scan.issueMutationId ??= randomId()
      const issued = await issueCodes(productId, 1, false, scan.issueMutationId)
      await printCodes(productId, issued.items)
    },
    [flushUnprinted, issueCodes, printCodes],
  )

  const scanKiz = useCallback(
    async (raw: string): Promise<string | null> => {
      // Подсказка товара действует только сразу после ШК этого товара.
      const productId = lastProductRef.current
      lastProductRef.current = null
      const result = await scanMarkingCode(apiContext(), { code: raw, productId, mutationId: randomId() })
      await reloadCodes()
      latest.current.onChanged()
      // R6: повтор того же КИЗ — нейтральное сообщение, без красного.
      return result.already_linked ? KIZ_ALREADY_LINKED_MESSAGE : null
    },
    [apiContext, reloadCodes],
  )

  const scanProduct = useCallback(
    async (raw: string, matchedProductId: string | null): Promise<void> => {
      lastProductRef.current = null
      const { currentBoxId, detail: current, prefs: printPrefs } = latest.current
      const boxId = currentBoxId && current.boxes.some((box) => box.id === currentBoxId) ? currentBoxId : null
      if (!boxId) throw new Error(NO_CURRENT_BOX_MESSAGE)
      // Тот же код в тот же короб после скана с неизвестным исходом продолжает его с прежними ключами.
      // Незавершённая операция забирается из карты и возвращается в неё, только если исход снова неизвестен.
      const scanKey = `${boxId}\u0000${raw}`
      const pending = pendingScansRef.current.get(scanKey)
      pendingScansRef.current.delete(scanKey)
      const scan: PendingScan = pending ?? {
        productId: matchedProductId,
        mutationId: randomId(),
        issueMutationId: null,
        unresolved: false,
      }
      scan.unresolved = false
      const mutationId = scan.mutationId
      try {
        // Ответ потерялся — штука могла лечь в короб: одна автоматическая попытка тем же запросом и ключом.
        let result: Awaited<ReturnType<typeof scanProductIntoBox>>
        try {
          result = await retryOnceIfOutcomeUnknown(() =>
            scanProductIntoBox(apiContext(), boxId, {
              barcode: raw,
              productId: scan.productId,
              mutationId,
            }),
          )
        } catch (cause) {
          if (isOutcomeUnknown(cause)) scan.unresolved = true
          throw cause
        }
        if (result.kind === 'ready_box') {
          latest.current.onChanged()
          return
        }
        if (result.kind !== 'product') {
          throw new Error('Это ШК ячейки или тары. На упаковке отсканируйте ШК товара, ЧЗ или короба.')
        }
        const productId = result.product_id ?? scan.productId
        lastProductRef.current = productId
        latest.current.onChanged()
        if (!productId) return
        // Штука уже в коробе; сбой печати не откатывает её, а сообщает отдельно.
        const failures: string[] = []
        const row = latest.current.rows.find((item) => item.productId === productId)
        if (printPrefs.printBarcode && row) {
          try {
            await printProductBarcodeLabels(
              productLabelData(metaOf(row), current.marketplace),
              `fbo-bc:${current.id}:${mutationId}`,
            )
          } catch (cause) {
            failures.push(errorText(cause, 'Не удалось напечатать ШК товара.'))
          }
        }
        if (printPrefs.printChz && latest.current.requiresChz(productId)) {
          try {
            await issueOneAndPrint(productId, scan)
          } catch (cause) {
            if (isOutcomeUnknown(cause)) scan.unresolved = true
            failures.push(errorText(cause, 'Не удалось выдать и напечатать ЧЗ.'))
          }
        }
        if (failures.length > 0) throw new Error(`Штука уложена в короб. ${failures.join(' ')}`)
      } finally {
        if (scan.unresolved) pendingScansRef.current.set(scanKey, scan)
      }
    },
    [apiContext, issueOneAndPrint, metaOf],
  )

  /**
   * Один скан со сканера или из поля. Отказ летит исключением: строка скана покажет его красным.
   * Возвращает нейтральное сообщение (без красного), если оно есть.
   */
  const handleScan = useCallback(
    async (rawInput: string): Promise<string | null> => {
      const raw = rawInput.trim()
      if (!raw) return null
      const { detail: current, productCodes: byProduct } = latest.current
      const kind = classifyScan(raw, current, byProduct)
      if (kind.kind === 'box') {
        lastProductRef.current = null
        await latest.current.onBoxBarcodeScanned(raw)
        return null
      }
      if (kind.kind === 'kiz') return scanKiz(raw)
      await scanProduct(raw, kind.productId)
      return null
    },
    [scanKiz, scanProduct],
  )

  const runForProduct = useCallback(
    async (productId: string, work: () => Promise<string | null>): Promise<void> => {
      setBusyProductId(productId)
      setRowMessage(productId, null)
      try {
        const notice = await work()
        if (notice) setRowMessage(productId, notice)
      } catch (cause) {
        setRowMessage(productId, errorText(cause, 'Действие не выполнено.'))
      } finally {
        setBusyProductId(null)
      }
    },
    [setRowMessage],
  )

  const reprintCode = useCallback(
    (code: FboMarkingCode) =>
      runForProduct(code.product_id, async () => {
        await printMarkingCodeLabel(code, latest.current.token, reprintKey(code))
        return null
      }),
    [runForProduct],
  )

  const unbindCode = useCallback(
    (code: FboMarkingCode) =>
      runForProduct(code.product_id, async () => {
        await deleteMarkingCode(apiContext(), code.marking_code_id)
        setUnprintedFor(
          code.product_id,
          (latest.current.unprinted[code.product_id] ?? []).filter((item) => item.marking_code_id !== code.marking_code_id),
        )
        await reloadCodes()
        latest.current.onChanged()
        return null
      }),
    [apiContext, reloadCodes, runForProduct, setUnprintedFor],
  )

  /**
   * Кнопка строки «ШК + ЧЗ» (не блокируется): N этикеток ШК товара (N = S, при S = 0 — план P) и,
   * если у товара включён ЧЗ, ТОЛЬКО недостающие коды: выдаёт из пула quantity = N − K и печатает выданные.
   * Уже привязанные коды не перепечатываются (перепечатка — из списка кодов). Нечего выдавать — печатаются
   * одни ШК без ошибки. Пустой пул — сообщение, ШК к этому моменту уже напечатаны.
   */
  const printLine = useCallback(
    (productId: string) =>
      runForProduct(productId, async () => {
        const { rows: current, detail: shipment } = latest.current
        const row = current.find((item) => item.productId === productId)
        if (!row) return null
        const target = printTargetOf(row)
        // Ключ печати ШК живёт, пока печать ШК не принята: повтор после сбоя не печатает принятые копии.
        const barcodeKey = lineBarcodeKeyRef.current.get(productId) ?? `fbo-bc:${shipment.id}:${randomId()}`
        lineBarcodeKeyRef.current.set(productId, barcodeKey)
        await printProductBarcodeLabels(productLabelData(metaOf(row), shipment.marketplace), barcodeKey, target)
        lineBarcodeKeyRef.current.delete(productId)
        if (!latest.current.requiresChz(productId)) return null
        // Выданные раньше, но не напечатанные коды — повтор той же печати, а не перепечатка.
        await flushUnprinted(productId)
        const missing = target - latest.current.kizCountOf(row)
        if (missing <= 0) return null
        let issued: FboMarkingIssueResult
        try {
          issued = await issueCodes(productId, missing)
        } catch (cause) {
          if (cause instanceof FboPackingApiError && cause.code === 'nothing_to_issue') return null
          throw cause
        }
        await printCodes(productId, issued.items)
        return shortageNotice(issued)
      }),
    [flushUnprinted, issueCodes, metaOf, printCodes, runForProduct],
  )

  /** «Печать накладной»: лист отгрузки по плану товаров отгрузки. */
  const printWaybill = useCallback((): void => {
    const { detail: shipment, rows: current } = latest.current
    printShipmentPackagingSheet({
      documentNumber: formatHumanDocumentNumber(shipment) ?? shipment.document_number ?? shipment.id,
      documentType: 'Отгрузка на маркетплейс',
      sellerName: shipment.seller_name,
      shipmentDate: shipment.created_at ? new Date(shipment.created_at).toLocaleString('ru-RU') : null,
      warehouseName: shipment.warehouse_name || 'Склад',
      createdAt: shipment.created_at ?? null,
      items: current.map((row) => {
        const meta = metaOf(row)
        return {
          product_name: meta.product_name,
          vendor_code: meta.wb_vendor_code ?? '',
          sku_code: meta.sku_code,
          barcode: productBarcodeForMarketplace(meta, shipment.marketplace) || null,
          wb_nm_id: meta.wb_nm_id,
          photo_url: meta.wb_primary_image_url,
          instructions: row.packagingInstructions ?? meta.packaging_instructions ?? null,
          quantity: row.need,
          size: meta.wb_size,
          color: meta.wb_color,
        }
      }),
    })
  }, [metaOf])

  return {
    rows,
    metaOf,
    codesByProduct,
    codesError,
    kizCountOf,
    requiresChz,
    prefs,
    setPrefs,
    handleScan,
    busyProductId,
    rowMessages,
    reprintCode,
    unbindCode,
    printLine,
    printWaybill,
  }
}

export type FboPackingController = ReturnType<typeof useFboPacking>
