import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type WithdrawalStatus =
  | 'not_withdrawn'
  | 'transferring'
  | 'awaiting_crpt'
  | 'withdrawn'
  | 'error'

export type WithdrawalErrorDetail = {
  source?: string
  code?: string
  message?: string
  [key: string]: unknown
}

export type WithdrawalRow = {
  row_id: string
  product_id: string | null
  delivered_at: string
  wb_order_id: string
  sku: string
  product_name: string
  cis: string
  status: WithdrawalStatus
  error: WithdrawalErrorDetail | null
  operation_id: string | null
  resume_required?: boolean
}

export type WithdrawalPage = {
  rows: WithdrawalRow[]
  total: number
}

export type WithdrawalProductOption = {
  id: string
  sku: string
  name: string
}

export type WithdrawalCertificateBinding = {
  thumbprint: string
  expires_at: string
  subject?: string
  issuer?: string
}

export type WithdrawalAuthChallenge = {
  uuid: string
  data: string
}

export type WithdrawalDocumentToSign = {
  document_id: string
  payload_base64: string
  payload_sha256: string
  thumbprint: string
}

export type WithdrawalOperationItem = {
  row_id: string
  cis: string
  wb_order_id: string
  status: WithdrawalStatus
  error: WithdrawalErrorDetail | null
}

export type WithdrawalOperation = {
  operation_id: string
  state: string
  attempt: number
  integration_gate: 'WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED' | null
  reauth_required: boolean
  certificate_thumbprint: string | null
  auth_challenge: WithdrawalAuthChallenge | null
  documents: WithdrawalDocumentToSign[]
  auth_error: WithdrawalErrorDetail | null
  items: WithdrawalOperationItem[]
}

export type WithdrawalRegistryQuery = {
  dateFrom: string
  dateTo: string
  search: string
  productId: string | null
  onlyNotWithdrawn: boolean
  limit: 50 | 100 | 250
  offset: number
}

export type WithdrawalDocumentSignatureInput = {
  document_id: string
  payload_sha256: string
  thumbprint: string
  signature: string
}

const ERROR_MESSAGES: Record<string, string> = {
  WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED:
    'Отправка в Честный знак в этом контуре пока отключена.',
  withdrawal_reauth_certificate_mismatch:
    'Для продолжения выберите тот же сертификат, которым была начата операция.',
  withdrawal_reauth_user_mismatch:
    'Продолжить эту операцию может только начавший её пользователь.',
  certificate_expired:
    'Срок действия сертификата истёк. Выберите действующий сертификат.',
  withdrawal_auth_signature_mismatch:
    'Данные авторизации уже изменились. Повторите подпись с тем же сертификатом.',
  invalid_date_range: 'Дата начала периода должна быть не позже даты окончания.',
  invalid_pagination: 'Не удалось открыть эту страницу реестра. Обновите данные.',
  invalid_selection: 'Выберите от 1 до 250 КИЗ на текущей странице.',
  withdrawal_rows_not_found: 'Часть выбранных КИЗ больше недоступна. Обновите реестр.',
  selection_overlaps_existing_operation:
    'Часть выбранных КИЗ уже обрабатывается в другой операции. Обновите реестр.',
  withdrawal_selection_conflict:
    'КИЗ уже выбраны в другой операции. Обновите реестр и повторите.',
  idempotency_selection_mismatch:
    'Состав операции изменился. Обновите реестр и выберите КИЗ заново.',
  withdrawal_not_found: 'Операция вывода из оборота не найдена.',
  attempt_mismatch: 'Состояние операции уже изменилось. Обновите реестр.',
}

export class WithdrawalApiError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(message: string, status: number, code: string | null) {
    super(message)
    this.name = 'WithdrawalApiError'
    this.status = status
    this.code = code
  }
}

const readStructuredError = async (response: Response): Promise<WithdrawalApiError> => {
  const clone = response.clone()
  try {
    const body = (await clone.json()) as {
      detail?: string | { code?: unknown; message?: unknown }
    }
    const detail = body.detail
    const code =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail.code === 'string'
          ? detail.code
          : null
    const explicit =
      detail && typeof detail === 'object' && typeof detail.message === 'string'
        ? detail.message
        : null
    return new WithdrawalApiError(
      explicit ?? (code ? ERROR_MESSAGES[code] : null) ?? (await readApiErrorMessage(response)),
      response.status,
      code,
    )
  } catch (error) {
    if (error instanceof WithdrawalApiError) return error
    return new WithdrawalApiError(await readApiErrorMessage(response), response.status, null)
  }
}

const jsonOrThrow = async <T>(response: Response): Promise<T> => {
  if (!response.ok) throw await readStructuredError(response)
  return (await response.json()) as T
}

export interface SellerWithdrawalApi {
  list(query: WithdrawalRegistryQuery, signal?: AbortSignal): Promise<WithdrawalPage>
  listProducts(search?: string, signal?: AbortSignal): Promise<WithdrawalProductOption[]>
  createOperation(input: {
    rowIds: string[]
    clientRequestId: string
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation>
  getOperation(operationId: string, signal?: AbortSignal): Promise<WithdrawalOperation>
  retryOperation(input: {
    operationId: string
    expectedAttempt: number
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation>
  requestReauthChallenge(input: {
    operationId: string
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation>
  submitAuthSignature(input: {
    operationId: string
    thumbprint: string
    signature: string
    challengeUuid: string
    expectedAttempt: number
  }): Promise<WithdrawalOperation>
  submitDocumentSignatures(input: {
    operationId: string
    documents: WithdrawalDocumentSignatureInput[]
  }): Promise<WithdrawalOperation>
}

export class SameOriginSellerWithdrawalApi implements SellerWithdrawalApi {
  readonly #token: string

  constructor(token: string) {
    this.#token = token
  }

  #headers(json = false): HeadersInit {
    return {
      Authorization: `Bearer ${this.#token}`,
      ...(json ? { 'Content-Type': 'application/json' } : {}),
    }
  }

  async list(query: WithdrawalRegistryQuery, signal?: AbortSignal): Promise<WithdrawalPage> {
    const params = new URLSearchParams({
      date_from: query.dateFrom,
      date_to: query.dateTo,
      only_not_withdrawn: String(query.onlyNotWithdrawn),
      limit: String(query.limit),
      offset: String(query.offset),
    })
    if (query.search.trim()) params.set('search', query.search.trim())
    if (query.productId) params.set('product_id', query.productId)
    const response = await fetch(
      apiUrl(`/operations/marking-codes/self/withdrawals?${params.toString()}`),
      { headers: this.#headers(), signal },
    )
    return jsonOrThrow<WithdrawalPage>(response)
  }

  async listProducts(search = '', signal?: AbortSignal): Promise<WithdrawalProductOption[]> {
    const params = new URLSearchParams({ limit: '100' })
    if (search.trim()) params.set('search', search.trim())
    const response = await fetch(
      apiUrl(`/operations/marking-codes/self/withdrawals/products?${params.toString()}`),
      { headers: this.#headers(), signal },
    )
    return jsonOrThrow<WithdrawalProductOption[]>(response)
  }

  async createOperation(input: {
    rowIds: string[]
    clientRequestId: string
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation> {
    const response = await fetch(
      apiUrl('/operations/marking-codes/self/withdrawals/operations'),
      {
        method: 'POST',
        headers: this.#headers(true),
        body: JSON.stringify({
          row_ids: input.rowIds,
          client_request_id: input.clientRequestId,
          certificate: input.certificate,
        }),
      },
    )
    return jsonOrThrow<WithdrawalOperation>(response)
  }

  async getOperation(operationId: string, signal?: AbortSignal): Promise<WithdrawalOperation> {
    const response = await fetch(
      apiUrl(`/operations/marking-codes/self/withdrawals/operations/${encodeURIComponent(operationId)}`),
      { headers: this.#headers(), signal },
    )
    return jsonOrThrow<WithdrawalOperation>(response)
  }

  async retryOperation(input: {
    operationId: string
    expectedAttempt: number
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation> {
    const response = await fetch(
      apiUrl(
        `/operations/marking-codes/self/withdrawals/operations/${encodeURIComponent(input.operationId)}/retry`,
      ),
      {
        method: 'POST',
        headers: this.#headers(true),
        body: JSON.stringify({
          expected_attempt: input.expectedAttempt,
          certificate: input.certificate,
        }),
      },
    )
    return jsonOrThrow<WithdrawalOperation>(response)
  }

  async requestReauthChallenge(input: {
    operationId: string
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation> {
    const response = await fetch(
      apiUrl(
        `/operations/marking-codes/self/withdrawals/operations/${encodeURIComponent(input.operationId)}/reauth-challenge`,
      ),
      {
        method: 'POST',
        headers: this.#headers(true),
        body: JSON.stringify({ certificate: input.certificate }),
      },
    )
    return jsonOrThrow<WithdrawalOperation>(response)
  }

  async submitAuthSignature(input: {
    operationId: string
    thumbprint: string
    signature: string
    challengeUuid: string
    expectedAttempt: number
  }): Promise<WithdrawalOperation> {
    const response = await fetch(
      apiUrl(
        `/operations/marking-codes/self/withdrawals/operations/${encodeURIComponent(input.operationId)}/auth-signature`,
      ),
      {
        method: 'POST',
        headers: this.#headers(true),
        body: JSON.stringify({
          thumbprint: input.thumbprint,
          signature: input.signature,
          challenge_uuid: input.challengeUuid,
          expected_attempt: input.expectedAttempt,
        }),
      },
    )
    return jsonOrThrow<WithdrawalOperation>(response)
  }

  async submitDocumentSignatures(input: {
    operationId: string
    documents: WithdrawalDocumentSignatureInput[]
  }): Promise<WithdrawalOperation> {
    const response = await fetch(
      apiUrl(
        `/operations/marking-codes/self/withdrawals/operations/${encodeURIComponent(input.operationId)}/document-signatures`,
      ),
      {
        method: 'POST',
        headers: this.#headers(true),
        body: JSON.stringify({ documents: input.documents }),
      },
    )
    return jsonOrThrow<WithdrawalOperation>(response)
  }
}

const TERMINAL_STATUS_MESSAGES: Record<string, string> = {
  CHECKED_NOT_OK: 'Честный знак отклонил документ.',
  PARSE_ERROR: 'Честный знак не смог прочитать документ.',
  PROCESSING_ERROR: 'Честный знак не смог обработать документ.',
}

const cleanProviderText = (value: unknown): string | null => {
  if (typeof value !== 'string' && typeof value !== 'number') return null
  const text = String(value).replace(/\s+/g, ' ').trim()
  return text ? text.slice(0, 500) : null
}

const collectProviderReasons = (value: unknown, depth = 0): string[] => {
  if (depth > 4 || value == null) return []
  const scalar = cleanProviderText(value)
  if (scalar) return [scalar]
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectProviderReasons(item, depth + 1))
  }
  if (typeof value !== 'object') return []

  const record = value as Record<string, unknown>
  const message =
    cleanProviderText(record.message) ??
    cleanProviderText(record.error_message) ??
    cleanProviderText(record.errorMessage) ??
    cleanProviderText(record.error) ??
    cleanProviderText(record.description)
  if (message) return [message]

  const detailReasons = collectProviderReasons(record.detail, depth + 1)
  if (detailReasons.length > 0) return detailReasons

  const nestedReasons = [record.errors, record.commonErrors, record.common_errors]
    .flatMap((nested) => collectProviderReasons(nested, depth + 1))
  if (nestedReasons.length > 0) return nestedReasons

  const code = cleanProviderText(record.code)
  return code ? [ERROR_MESSAGES[code] ?? code] : []
}

export const withdrawalErrorMessage = (error: WithdrawalErrorDetail | null | undefined): string => {
  if (!error) return ''

  const directMessage = cleanProviderText(error.message)
    ?? cleanProviderText(error.error_message)
    ?? cleanProviderText(error.errorMessage)
  if (directMessage) return directMessage

  const reasons = [error.errors, error.commonErrors, error.common_errors]
    .flatMap((value) => collectProviderReasons(value))
    .filter((value, index, values) => values.indexOf(value) === index)
    .slice(0, 4)
  if (reasons.length > 0) return reasons.join(' · ')

  const directError = cleanProviderText(error.error) ?? cleanProviderText(error.description)
  if (directError) return directError

  const detailReasons = collectProviderReasons(error.detail)
  if (detailReasons.length > 0) return detailReasons.slice(0, 4).join(' · ')

  const code = cleanProviderText(error.code)
  if (code) return ERROR_MESSAGES[code] ?? code

  const status = cleanProviderText(error.status)
  return status ? TERMINAL_STATUS_MESSAGES[status] ?? '' : ''
}

export const withdrawalApiErrorMessage = (error: unknown): string => {
  if (error instanceof Error && error.message.trim()) return error.message
  return 'Не удалось выполнить операцию. Обновите данные и повторите.'
}
