import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import type {
  FboBoxScanResult,
  FboMarkingCode,
  FboMarkingIssueResult,
  FboMarkingScanResult,
} from './fboPackingTypes'

export type FboPackingApiContext = {
  requestId: string
  headers: HeadersInit
}

/** Отказ сервера или обрыв связи. code — машинный код отказа, если сервер его прислал. */
export class FboPackingApiError extends Error {
  readonly code: string | null
  readonly status: number

  constructor(message: string, code: string | null, status: number) {
    super(message)
    this.name = 'FboPackingApiError'
    this.code = code
    this.status = status
  }

  /** Ответ мог потеряться: повтор с тем же mutation_id вернёт тот же результат. */
  get outcomeUnknown(): boolean {
    return this.status === 0 || this.status >= 500
  }
}

/** Тексты отказов упаковки FBO: раздел 5.8 ТЗ WMS-686 (те же, что в общем словаре readApiErrorMessage). */
export const FBO_PACKING_MESSAGES_RU: Record<string, string> = {
  marking_code_invalid: 'Не похоже на код Честного знака. Отсканируйте КИЗ заново целиком.',
  marking_product_unknown: 'Сначала отсканируйте ШК товара.',
  marking_code_other_product: 'Этот КИЗ относится к другому товару.',
  marking_code_other_shipment: 'Этот КИЗ уже привязан к другой отгрузке.',
  marking_code_used_elsewhere: 'Этот КИЗ уже использован в другом процессе.',
  marking_quantity_exceeded: 'Сначала отсканируйте ШК следующей штуки.',
  marking_pool_empty: 'В пуле нет свободных КИЗ этого товара.',
  nothing_to_issue: 'Все подобранные штуки уже с КИЗ.',
  box_already_attached: 'Этот короб уже в отгрузке.',
  barcode_unknown: 'Штрихкод не найден. Проверьте товар.',
  product_not_in_shipment: 'Этого товара нет в составе отгрузки.',
  plan_limit_exceeded: 'Нельзя добавить больше, чем в плане отгрузки.',
  plan_exceeded: 'Нельзя добавить больше, чем в плане отгрузки.',
  // На упаковке товар уже подобран: эти отказы значат «подобранных штук не осталось».
  location_required: 'Нет подобранных штук этого товара. Сначала подберите товар.',
  insufficient_available: 'Нет подобранных штук этого товара. Сначала подберите товар.',
  insufficient_free_fbo: 'Нет подобранных штук этого товара. Сначала подберите товар.',
  box_not_found: 'Короб не найден. Выберите короб заново.',
}

export const FBO_NETWORK_ERROR_RU = 'Нет связи с сервером. Проверьте соединение и повторите.'

function detailCode(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const code = (detail as { code?: unknown }).code
    if (typeof code === 'string') return code
  }
  return null
}

async function toApiError(response: Response): Promise<FboPackingApiError> {
  const text = await response.text().catch(() => '')
  let code: string | null = null
  try {
    const parsed = JSON.parse(text) as { detail?: unknown }
    code = detailCode(parsed.detail)
  } catch {
    code = null
  }
  if (code && FBO_PACKING_MESSAGES_RU[code]) {
    return new FboPackingApiError(FBO_PACKING_MESSAGES_RU[code]!, code, response.status)
  }
  // Остальные коды и тексты — общий разбор ответа приложения.
  const message = await readApiErrorMessage(new Response(text, { status: response.status }))
  return new FboPackingApiError(message, code, response.status)
}

function jsonHeaders(ctx: FboPackingApiContext): Headers {
  const headers = new Headers(ctx.headers)
  headers.set('Content-Type', 'application/json')
  return headers
}

function url(ctx: FboPackingApiContext, path: string): string {
  return apiUrl(`/operations/marketplace-unload-requests/${ctx.requestId}${path}`)
}

async function send(input: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init)
  } catch {
    throw new FboPackingApiError(FBO_NETWORK_ERROR_RU, 'network', 0)
  }
}

async function postJson<T>(ctx: FboPackingApiContext, path: string, body: unknown): Promise<T> {
  const response = await send(url(ctx, path), {
    method: 'POST',
    headers: jsonHeaders(ctx),
    body: JSON.stringify(body),
  })
  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as T
}

/** Тот же серверный путь, что «Наполнить»: сначала подобранные, но не уложенные штуки. */
export function scanProductIntoBox(
  ctx: FboPackingApiContext,
  boxId: string,
  input: { barcode: string; productId: string | null; mutationId: string },
): Promise<FboBoxScanResult> {
  return postJson<FboBoxScanResult>(ctx, `/boxes/${boxId}/scan`, {
    mutation_id: input.mutationId,
    barcode: input.barcode,
    quantity: 1,
    allow_over_plan: false,
    ...(input.productId ? { product_id: input.productId } : {}),
  })
}

export function scanMarkingCode(
  ctx: FboPackingApiContext,
  input: { code: string; productId: string | null; mutationId: string },
): Promise<FboMarkingScanResult> {
  return postJson<FboMarkingScanResult>(ctx, '/marking-codes/scan', {
    code: input.code,
    mutation_id: input.mutationId,
    ...(input.productId ? { product_id: input.productId } : {}),
  })
}

export async function listMarkingCodes(ctx: FboPackingApiContext): Promise<FboMarkingCode[]> {
  const response = await send(url(ctx, '/marking-codes'), { headers: new Headers(ctx.headers) })
  if (!response.ok) throw await toApiError(response)
  const body = (await response.json()) as { items?: FboMarkingCode[] }
  return Array.isArray(body.items) ? body.items : []
}

export async function deleteMarkingCode(ctx: FboPackingApiContext, markingCodeId: string): Promise<void> {
  const response = await send(url(ctx, `/marking-codes/${markingCodeId}`), {
    method: 'DELETE',
    headers: new Headers(ctx.headers),
  })
  if (!response.ok) throw await toApiError(response)
}

/** Выдача свободных кодов товара из пула. Тот же mutation_id возвращает те же коды. */
export async function issueMarkingCodes(
  ctx: FboPackingApiContext,
  input: { productId: string; quantity?: number; mutationId: string },
): Promise<FboMarkingIssueResult> {
  const result = await postJson<Partial<FboMarkingIssueResult>>(ctx, '/marking-codes/issue', {
    product_id: input.productId,
    mutation_id: input.mutationId,
    ...(input.quantity !== undefined ? { quantity: input.quantity } : {}),
  })
  return { items: Array.isArray(result.items) ? result.items : [], shortage: result.shortage ?? 0 }
}
