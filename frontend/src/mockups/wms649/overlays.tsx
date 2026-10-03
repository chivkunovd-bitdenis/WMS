import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Box, MenuItem, TextField, ToggleButton, ToggleButtonGroup } from '@mui/material'

import {
  getDefaultCode,
  orderedCodes,
  PRODUCTS,
  setDefaultCode,
  useDefaults,
  type DemoProduct,
  type Marketplace,
} from './products'
import { setNativeSelectValue, useHost, useNodeText } from './hosts'
import { fixedPlatform, platformsOf } from './platforms'

/**
 * WMS-649 · единственные новые элементы макета.
 *
 * 1. Окно печати (настоящий MarkingPrintDialog). Если площадка известна из
 *    документа — вопроса нет, печатается ШК этой площадки. Если неизвестна:
 *    у товара «только WB / только Ozon» вопроса тоже нет, у «микса» наверху окна
 *    стоит переключатель «Для WB | Для Ozon» — на том месте, где сегодня стоит
 *    общий список «Площадка и штрихкод». Остальное окно — настоящее.
 * 2. Карточка товара (настоящий ProductCardDialog). Там, где у площадки больше
 *    одного кода, строка «ШК» становится выбором кода по умолчанию.
 */

const DIALOG = '[data-testid="marking-print-dialog"]'
const REAL_SELECT = 'marking-print-product-barcode-select'

export function PlatformToggle({
  value,
  onChange,
  disabled,
}: {
  value: Marketplace
  onChange: (next: Marketplace) => void
  disabled?: boolean
}) {
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={value}
      disabled={disabled}
      onChange={(_event, next: Marketplace | null) => {
        if (next) onChange(next)
      }}
      data-testid="wms649-platform-toggle"
    >
      <ToggleButton value="wb" data-testid="wms649-platform-wb">
        Для WB
      </ToggleButton>
      <ToggleButton value="ozon" data-testid="wms649-platform-ozon">
        Для Ozon
      </ToggleButton>
    </ToggleButtonGroup>
  )
}

/**
 * Накладывается на настоящее окно печати (MarkingPrintDialog).
 * `docPlatform` — площадка документа, из которого открыли окно; null — документ
 * площадку не определяет (каталог, приёмка, Честный знак).
 */
/** Товар по тексту шапки окна: его SKU, SKU площадки Ozon или название. */
function productFromHeader(text: string): DemoProduct | undefined {
  if (!text) return undefined
  return PRODUCTS.find(
    (item) =>
      text.includes(item.sku) || (item.ozon !== null && text.includes(item.ozon.sku)) || text.includes(item.name),
  )
}

export function MarkingDialogOverlay({ docPlatform }: { docPlatform: Marketplace | null }) {
  const headerText = useNodeText(`${DIALOG} [data-testid="marking-print-header"]`, null)
  const dialogOpen = headerText.length > 0
  const product = productFromHeader(headerText)

  // Каждое открытие окна — новый «сеанс»: выбор сбрасывается к умолчанию.
  // Номер сеанса меняем прямо при рендере (так React советует подстраивать состояние
  // под входные данные), а не отдельным эффектом.
  const [wasOpen, setWasOpen] = useState(false)
  const [session, setSession] = useState(0)
  if (dialogOpen !== wasOpen) {
    setWasOpen(dialogOpen)
    if (dialogOpen) setSession((value) => value + 1)
  }

  const [choiceState, setChoiceState] = useState<{ session: number; value: Marketplace }>({
    session: 0,
    value: 'wb',
  })
  const choice: Marketplace = choiceState.session === session ? choiceState.value : 'wb'
  const setChoice = (value: Marketplace) => setChoiceState({ session, value })

  // Площадка документа задана — вопроса нет. Не задана: у товара с одной площадкой
  // вопроса тоже нет, у «микса» оператор выбирает.
  const fixed = product ? fixedPlatform(product, docPlatform) : docPlatform
  const needsChoice = Boolean(product) && fixed === null
  const effective: Marketplace | null = product ? (fixed ?? choice) : fixed

  const host = useHost(
    needsChoice
      ? { id: 'marking-choice', selector: `${DIALOG} .MuiDialogContent-root > div`, placement: 'first-child' }
      : null,
  )

  // Настоящий список «Площадка и штрихкод» остаётся источником состояния окна:
  // переключатель лишь выставляет в нём первый (умолчательный) код нужной площадки.
  useEffect(() => {
    if (!product || !effective) return
    const wanted = `${effective}:${orderedCodes(product, effective)[0] ?? ''}`
    let done = false
    const run = () => {
      if (done) return
      if (setNativeSelectValue(document, REAL_SELECT, wanted)) done = true
    }
    run()
    const observer = new MutationObserver(run)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [product, effective, session])

  return (
    <>
      <style>{`${DIALOG} [data-testid="${REAL_SELECT}"] { display: none !important; }`}</style>
      {host && product
        ? createPortal(
            <Box data-testid="wms649-choice">
              <PlatformToggle value={choice} onChange={setChoice} />
            </Box>,
            host,
          )
        : null}
    </>
  )
}

/** Выбор ШК по умолчанию в блоке площадки карточки товара. */
function DefaultCodeSelect({ product, marketplace }: { product: DemoProduct; marketplace: Marketplace }) {
  useDefaults()
  const codes = marketplace === 'wb' ? product.wbCodes : product.ozonCodes
  const value = getDefaultCode(product, marketplace) ?? ''
  return (
    <TextField
      select
      size="small"
      label="ШК по умолчанию"
      value={value}
      onChange={(event) => setDefaultCode(product.id, marketplace, event.target.value)}
      sx={{ minWidth: 240 }}
      data-testid={`wms649-default-${marketplace}`}
    >
      {codes.map((code) => (
        <MenuItem key={code} value={code}>
          {code}
        </MenuItem>
      ))}
    </TextField>
  )
}

/** Накладывается на настоящую карточку товара (ProductCardDialog → вкладка «Основное»). */
export function ProductCardOverlay() {
  const sku = useNodeText('[data-testid="product-card-field-sku"]', null)
  const product = PRODUCTS.find((item) => item.sku === sku.trim())

  const wbHost = useHost(
    product && product.wbCodes.length > 1
      ? {
          id: 'card-default-wb',
          selector: '[data-testid="product-card-wb-barcodes"]',
          placement: 'after',
          hideTarget: true,
        }
      : null,
  )
  const ozonHost = useHost(
    product && product.ozonCodes.length > 1
      ? {
          id: 'card-default-ozon',
          selector: '[data-testid="product-card-ozon-barcodes"]',
          placement: 'after',
          hideTarget: true,
        }
      : null,
  )

  if (!product) return null
  return (
    <>
      {wbHost ? createPortal(<DefaultCodeSelect product={product} marketplace="wb" />, wbHost) : null}
      {ozonHost ? createPortal(<DefaultCodeSelect product={product} marketplace="ozon" />, ozonHost) : null}
    </>
  )
}

const LABEL_DIALOG = '[data-testid="ff-product-label-print-dialog"]'

/** Заменяет в тексте окна «WB»-подписи на подписи выбранной площадки. */
function relabelDialog(root: HTMLElement, platform: Marketplace): void {
  const wanted = platform === 'ozon' ? 'Ozon' : 'WB'
  const wantedShort = platform === 'ozon' ? 'ШК Ozon' : 'ШК ВБ'
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    const text = node.textContent ?? ''
    const next = text
      .replace(/Этикетка (?:WB|Ozon)/, `Этикетка ${wanted}`)
      .replace(/ШК (?:ВБ|Ozon)/, wantedShort)
    if (next !== text) node.textContent = next
    node = walker.nextNode()
  }
}

/**
 * Накладывается на настоящее окно ProductBarcodePrintDialog (кабинет селлера).
 * Окно WB-шное целиком: его заголовок и подписи написаны про WB. Для «микса»
 * наверху окна появляется тот же переключатель «Для WB | Для Ozon», а подписи
 * окна следуют за выбором. Выбранную площадку держит родитель: именно по ней
 * он собирает данные товара для настоящего окна.
 */
export function ProductDialogOverlay({
  product,
  platform,
  onPlatform,
}: {
  product: DemoProduct | null
  platform: Marketplace
  onPlatform: (next: Marketplace) => void
}) {
  const needsChoice = product !== null && platformsOf(product).length > 1
  const host = useHost(
    needsChoice
      ? { id: 'label-choice', selector: `${LABEL_DIALOG} .MuiDialogContent-root`, placement: 'first-child' }
      : null,
  )

  useEffect(() => {
    if (!product) return
    const apply = () => {
      const root = document.querySelector<HTMLElement>(LABEL_DIALOG)
      if (root) relabelDialog(root, platform)
    }
    apply()
    const observer = new MutationObserver(apply)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [product, platform])

  return host && product ? (
    <>
      {createPortal(
        <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center' }} data-testid="wms649-choice">
          <PlatformToggle value={platform} onChange={onPlatform} />
        </Box>,
        host,
      )}
    </>
  ) : null
}
