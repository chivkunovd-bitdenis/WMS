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
export const NOTHING_TO_ISSUE_MESSAGE = 'КИЗ на все нужные штуки уже есть'

function errorText(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback
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
   * Печать кодов по очереди. Новые (только что выданные или ещё не напечатанные) идут стабильным
   * ключом первой печати, остальные — явной перепечатью с новым ключом. Невышедшие новые коды
   * запоминаются: повтор печатает ровно их, новые не выдаются.
   */
  const printCodes = useCallback(
    async (productId: string, list: FboMarkingCode[], newIds?: ReadonlySet<string>): Promise<void> => {
      const keyOf = (code: FboMarkingCode) =>
        !newIds || newIds.has(code.marking_code_id) ? firstPrintKey(code) : reprintKey(code)
      const outcome = await printMarkingCodes(list, latest.current.token, keyOf)
      const tracked = newIds
        ? outcome.unprinted.filter((code) => newIds.has(code.marking_code_id))
        : outcome.unprinted
      setUnprintedFor(productId, tracked)
      if (outcome.error) {
        throw new Error(
          tracked.length > 0
            ? `Коды выданы и привязаны, но печать не удалась: ${outcome.error.message}`
            : `Печать не удалась: ${outcome.error.message}`,
        )
      }
    },
    [setUnprintedFor],
  )

  /**
   * Выдача свободных кодов товара из пула. Кнопки («Допечатать», «ШК + ЧЗ») хранят ключ операции до
   * успешного ответа: после потери ответа повтор вернёт те же коды. Скан штуки берёт новый ключ каждый раз.
   */
  const issueCodes = useCallback(
    async (productId: string, quantity: number | undefined, reuseKey = true): Promise<FboMarkingIssueResult> => {
      const mutationKey = `${productId}:${quantity ?? 'all'}`
      const mutationId = (reuseKey ? issueMutationRef.current.get(mutationKey) : undefined) ?? randomId()
      if (reuseKey) issueMutationRef.current.set(mutationKey, mutationId)
      let issued: FboMarkingIssueResult
      try {
        issued = await issueMarkingCodes(apiContext(), { productId, quantity, mutationId })
      } catch (cause) {
        // Потерянный ответ: ключ остаётся, повтор вернёт те же коды. Отказ сервера снимает ключ.
        if (!(cause instanceof FboPackingApiError && cause.outcomeUnknown)) {
          issueMutationRef.current.delete(mutationKey)
        }
        throw cause
      }
      issueMutationRef.current.delete(mutationKey)
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
      await printCodes(productId, pending, new Set(pending.map((code) => code.marking_code_id)))
      return true
    },
    [printCodes],
  )

  /** Скан штуки с «Печатать ЧЗ»: один код на штуку (quantity=1), привязать и напечатать. */
  const issueOneAndPrint = useCallback(
    async (productId: string): Promise<void> => {
      await flushUnprinted(productId)
      const issued = await issueCodes(productId, 1, false)
      await printCodes(productId, issued.items, new Set(issued.items.map((code) => code.marking_code_id)))
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
      const mutationId = randomId()
      const result = await scanProductIntoBox(apiContext(), boxId, {
        barcode: raw,
        productId: matchedProductId,
        mutationId,
      })
      if (result.kind === 'ready_box') {
        latest.current.onChanged()
        return
      }
      if (result.kind !== 'product') {
        throw new Error('Это ШК ячейки или тары. На упаковке отсканируйте ШК товара, ЧЗ или короба.')
      }
      const productId = result.product_id ?? matchedProductId
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
          await issueOneAndPrint(productId)
        } catch (cause) {
          failures.push(errorText(cause, 'Не удалось выдать и напечатать ЧЗ.'))
        }
      }
      if (failures.length > 0) throw new Error(`Штука уложена в короб. ${failures.join(' ')}`)
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

  /**
   * «Допечатать» (кнопка всегда активна): выдать из пула недостающие коды (количество по умолчанию:
   * S − K при S > 0, иначе P − K) и напечатать их; если выданные раньше коды не напечатались —
   * повторить печать ровно их.
   */
  const reissueMissing = useCallback(
    (productId: string) =>
      runForProduct(productId, async () => {
        if (await flushUnprinted(productId)) return null
        const row = latest.current.rows.find((item) => item.productId === productId)
        if (!row) return null
        if (printTargetOf(row) - latest.current.kizCountOf(row) <= 0) return NOTHING_TO_ISSUE_MESSAGE
        let issued: FboMarkingIssueResult
        try {
          issued = await issueCodes(productId, undefined)
        } catch (cause) {
          if (cause instanceof FboPackingApiError && cause.code === 'nothing_to_issue') return NOTHING_TO_ISSUE_MESSAGE
          throw cause
        }
        await printCodes(productId, issued.items, new Set(issued.items.map((code) => code.marking_code_id)))
        return shortageNotice(issued)
      }),
    [flushUnprinted, issueCodes, printCodes, runForProduct],
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
   * Кнопка строки «ШК + ЧЗ» (R51, не блокируется): N этикеток ШК товара (N = S, при S = 0 — план P) и,
   * если у товара включён ЧЗ, недостающие коды из пула, затем печать всех кодов товара в отгрузке.
   * Пустой пул и «выдавать нечего» не отменяют печать уже привязанных кодов.
   */
  const printLine = useCallback(
    (productId: string) =>
      runForProduct(productId, async () => {
        const { rows: current, detail: shipment } = latest.current
        const row = current.find((item) => item.productId === productId)
        if (!row) return null
        await printProductBarcodeLabels(
          productLabelData(metaOf(row), shipment.marketplace),
          `fbo-bc:${shipment.id}:${randomId()}`,
          printTargetOf(row),
        )
        if (!latest.current.requiresChz(productId)) return null
        const existing = latest.current.codesByProduct.get(productId) ?? []
        const newIds = new Set((latest.current.unprinted[productId] ?? []).map((code) => code.marking_code_id))
        let issued: FboMarkingIssueResult = { items: [], shortage: 0 }
        let issueFailure: Error | null = null
        if (printTargetOf(row) - latest.current.kizCountOf(row) > 0) {
          try {
            issued = await issueCodes(productId, undefined)
            for (const code of issued.items) newIds.add(code.marking_code_id)
          } catch (cause) {
            const harmless = cause instanceof FboPackingApiError && cause.code === 'nothing_to_issue'
            if (!harmless) issueFailure = cause instanceof Error ? cause : new Error('Не удалось выдать коды ЧЗ.')
          }
        }
        const known = new Set(existing.map((code) => code.marking_code_id))
        const all = [...existing, ...issued.items.filter((code) => !known.has(code.marking_code_id))]
        await printCodes(productId, all, newIds)
        if (issueFailure) throw issueFailure
        return shortageNotice(issued)
      }),
    [issueCodes, metaOf, printCodes, runForProduct],
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
    hasUnprinted: (productId: string) => (unprinted[productId]?.length ?? 0) > 0,
    reissueMissing,
    reprintCode,
    unbindCode,
    printLine,
    printWaybill,
  }
}

export type FboPackingController = ReturnType<typeof useFboPacking>
