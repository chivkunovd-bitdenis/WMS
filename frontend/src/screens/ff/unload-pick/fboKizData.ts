import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'

// WMS-686 · подбор отгрузки FBO: данные и действия с КИЗ без разметки (компоненты — в fboPickKiz.tsx).

/** Код маркировки, привязанный к строке отгрузки (ответ GET .../marking-codes). */
export type FboKizCode = {
  marking_code_id: string
  cis_code: string
  product_id: string
  line_id: string | null
  status: string
  intake_document_number: string | null
  linked_at: string | null
  has_label_artifact: boolean
}

/** Ответ POST .../marking-codes/scan. */
export type FboKizScanResponse = {
  marking_code_id: string
  cis_code: string
  product_id: string
  line_id: string | null
  already_linked: boolean
  kiz_count: number
  picked_qty: number
}

/** Сколько КИЗ у каждого товара отгрузки. */
export function kizCountsByProduct(codes: FboKizCode[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const code of codes) counts.set(code.product_id, (counts.get(code.product_id) ?? 0) + 1)
  return counts
}

export function kizCodesOfProduct(codes: FboKizCode[], productId: string): FboKizCode[] {
  return codes.filter((code) => code.product_id === productId)
}

const GS = String.fromCharCode(29)

/** Разделитель GS в коде не печатается — показываем его видимым значком. */
export function kizDisplayCode(code: string): string {
  return code.split(GS).join('␝')
}

// Тексты по разделу 5.8 постановки WMS-686. Общий словарь readApiErrorMessage ведёт FE-PACK;
// здесь те же формулировки, чтобы подбор не зависел от порядка выкладки.
const KIZ_ERRORS: Record<string, string> = {
  marking_code_invalid: 'Не похоже на код Честного знака. Отсканируйте КИЗ заново целиком.',
  marking_product_unknown: 'Сначала отсканируйте ШК товара.',
  marking_code_other_product: 'Этот КИЗ относится к другому товару.',
  marking_code_other_shipment: 'Этот КИЗ уже привязан к другой отгрузке.',
  marking_code_used_elsewhere: 'Этот КИЗ уже использован в другом процессе.',
  marking_quantity_exceeded: 'Сначала отсканируйте ШК следующей штуки.',
}

async function readDetail(res: Response): Promise<{ text: string; detail: unknown }> {
  let text = ''
  try {
    text = await res.text()
  } catch {
    return { text, detail: undefined }
  }
  try {
    return { text, detail: (JSON.parse(text) as { detail?: unknown }).detail }
  } catch {
    return { text, detail: undefined }
  }
}

/** Текст отказа сервера по КИЗ: известные коды — по-русски, остальное — как отдал сервер. */
export async function readFboKizError(res: Response): Promise<string> {
  const { text, detail } = await readDetail(res)
  if (typeof detail === 'string' && KIZ_ERRORS[detail]) return KIZ_ERRORS[detail]
  if (detail && typeof detail === 'object') {
    const code = (detail as { code?: unknown }).code
    const message = (detail as { message?: unknown }).message
    if (typeof code === 'string' && KIZ_ERRORS[code] && !(typeof message === 'string' && message.trim())) {
      return KIZ_ERRORS[code]
    }
  }
  return readApiErrorMessage(new Response(text, { status: res.status }))
}

/** pick/scan не узнал код: ни товар, ни ячейка, ни тара — тогда это может быть КИЗ (R7). */
export async function isUnknownBarcodeResponse(res: Response): Promise<boolean> {
  const { detail } = await readDetail(res.clone())
  return detail === 'barcode_unknown'
}

export type FboBoxRefusal = {
  message: string
  /** Повтор переноса уже перенесённого короба: показывается спокойно, без красного и звука ошибки. */
  neutral: boolean
}

/** Отказ «Забрать короб целиком»: текст detail.message, а без него — из items (раздел 5.8). */
export async function readFboBoxRefusal(res: Response): Promise<FboBoxRefusal> {
  const { text, detail } = await readDetail(res)
  if (detail === 'box_already_attached') return { message: 'Этот короб уже в отгрузке.', neutral: true }
  if (detail === 'box_empty') return { message: 'В коробе нет товара.', neutral: true }
  if (detail && typeof detail === 'object') {
    const { code, message, items } = detail as { code?: unknown; message?: unknown; items?: unknown }
    if (typeof message === 'string' && message.trim()) return { message, neutral: false }
    if (code === 'plan_limit_exceeded' && Array.isArray(items) && items.length > 0) {
      const parts = items.map((item: { product_name?: string; product_id?: string; in_box?: number; remaining?: number }) =>
        `${item.product_name ?? item.product_id ?? 'товар'} — в коробе ${item.in_box ?? '?'}, осталось ${item.remaining ?? 0}`,
      )
      return {
        message: `Количество товаров в коробе больше, чем осталось подобрать: ${parts.join('; ')}. Откройте короб и подберите поштучно`,
        neutral: false,
      }
    }
  }
  return { message: await readApiErrorMessage(new Response(text, { status: res.status })), neutral: false }
}

/** Печать этикетки ЧЗ в WMS Print — тем же способом, что перепечатка ЧЗ в упаковке FBS. */
export async function printFboKizLabel(
  code: FboKizCode,
  token: string,
  idempotencyKey: string,
): Promise<void> {
  const [{ renderCzLabelPng }, { printPreparedQr }, { loadLabelSizeId, resolveLabelSize }] = await Promise.all([
    import('../../../utils/czLabelPng'),
    import('../../../utils/printPreparedQr'),
    import('../../../utils/labelSize'),
  ])
  const size = resolveLabelSize(loadLabelSizeId())
  const imageDataUrl = await renderCzLabelPng(
    { cis: code.cis_code, codeId: code.marking_code_id, hasLabelArtifact: code.has_label_artifact },
    size,
    token,
  )
  await printPreparedQr({ imageDataUrl, idempotencyKey, widthMm: size.widthMm, heightMm: size.heightMm })
}
