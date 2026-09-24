import { useMemo } from 'react'
import { Alert, Stack } from '@mui/material'

import type { CryptoProCertificate } from '../../integrations/cryptoProCades'
import { SellerKizWithdrawalScreen, type WithdrawalSigningAdapter } from './SellerKizWithdrawalScreen'
import {
  type SellerWithdrawalApi,
  type WithdrawalCertificateBinding,
  type WithdrawalDocumentSignatureInput,
  type WithdrawalOperation,
  type WithdrawalPage,
  type WithdrawalProductOption,
  type WithdrawalRegistryQuery,
  type WithdrawalRow,
} from './sellerKizWithdrawalApi'
import { sha256Base64Payload } from './sellerKizWithdrawalState'

const PRODUCT_OPTIONS: WithdrawalProductOption[] = [
  { id: '10000000-0000-4000-8000-000000000001', sku: 'WB-TSHIRT-BASE', name: 'Футболка базовая хлопковая' },
  { id: '10000000-0000-4000-8000-000000000002', sku: 'WB-HOODIE-OVERSIZE', name: 'Худи оверсайз с начёсом' },
  { id: '10000000-0000-4000-8000-000000000003', sku: 'WB-SOCKS-SPORT', name: 'Носки спортивные, 3 пары' },
  { id: '10000000-0000-4000-8000-000000000004', sku: 'WB-SNEAKERS-RUN', name: 'Кроссовки беговые' },
]

type DemoRow = WithdrawalRow & { submitFailure?: boolean }

const createRows = (): DemoRow[] => Array.from({ length: 324 }, (_, index) => {
  const sequence = index + 1
  const product = PRODUCT_OPTIONS[index % PRODUCT_OPTIONS.length]
  const error = sequence === 3
  const withdrawn = sequence % 41 === 0
  const date = 18 + (sequence % 7)
  return {
    row_id: `20000000-0000-4000-8000-${String(sequence).padStart(12, '0')}`,
    product_id: product.id,
    delivered_at: `2026-09-${String(date).padStart(2, '0')}T09:30:00Z`,
    wb_order_id: String(1849067400 + sequence),
    sku: `${product.sku}-${1000 + sequence}`,
    product_name: `${product.name} · модель ${1000 + sequence}`,
    cis: `01${String(4601234500000 + sequence).padStart(14, '0')}21${sequence.toString(36).padStart(8, '0')}WmsAcceptanceGS`,
    status: error ? 'error' : withdrawn ? 'withdrawn' : 'not_withdrawn',
    error: error ? { source: 'crpt', code: 'product_cost_missing', message: 'ЧЗ не принял документ: цена продажи не указана' } : null,
    operation_id: null,
    submitFailure: error,
  }
})

const copyOperation = (operation: WithdrawalOperation): WithdrawalOperation =>
  structuredClone(operation)

class AcceptanceWithdrawalApi implements SellerWithdrawalApi {
  #rows = createRows()
  #operations = new Map<string, WithdrawalOperation>()
  #operationRows = new Map<string, string[]>()

  async list(query: WithdrawalRegistryQuery): Promise<WithdrawalPage> {
    const needle = query.search.trim().toLocaleLowerCase('ru')
    const rows = this.#rows.filter((row) => {
      const date = row.delivered_at.slice(0, 10)
      if (date < query.dateFrom || date > query.dateTo) return false
      if (query.productId && row.product_id !== query.productId) return false
      if (query.onlyNotWithdrawn && row.status === 'withdrawn') return false
      if (needle && !`${row.product_name} ${row.sku} ${row.wb_order_id} ${row.cis}`.toLocaleLowerCase('ru').includes(needle)) return false
      return true
    })
    return { rows: rows.slice(query.offset, query.offset + query.limit), total: rows.length }
  }

  async listProducts(search = ''): Promise<WithdrawalProductOption[]> {
    const needle = search.trim().toLocaleLowerCase('ru')
    return needle
      ? PRODUCT_OPTIONS.filter((product) =>
          `${product.name} ${product.sku}`.toLocaleLowerCase('ru').includes(needle),
        )
      : PRODUCT_OPTIONS
  }

  async createOperation(input: {
    rowIds: string[]
    clientRequestId: string
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation> {
    const existing = [...this.#operations.values()].find((operation) =>
      operation.operation_id.endsWith(input.clientRequestId.slice(-12)),
    )
    if (existing) return copyOperation(existing)
    const operationId = `30000000-0000-4000-8000-${input.clientRequestId.replaceAll('-', '').slice(-12)}`
    const selected = this.#rows.filter((row) => input.rowIds.includes(row.row_id))
    const operation: WithdrawalOperation = {
      operation_id: operationId,
      state: 'auth_pending',
      attempt: 1,
      integration_gate: null,
      auth_challenge: { uuid: `challenge-${input.clientRequestId}`, data: `WMS517-${input.clientRequestId}` },
      documents: [],
      auth_error: null,
      items: selected.map((row) => ({
        row_id: row.row_id,
        cis: row.cis,
        wb_order_id: row.wb_order_id,
        status: 'not_withdrawn',
        error: null,
      })),
    }
    this.#operations.set(operationId, operation)
    this.#operationRows.set(operationId, input.rowIds)
    return copyOperation(operation)
  }

  async getOperation(operationId: string): Promise<WithdrawalOperation> {
    const operation = this.#operations.get(operationId)
    if (!operation) throw new Error('Операция не найдена')
    return copyOperation(operation)
  }

  async retryOperation(input: {
    operationId: string
    expectedAttempt: number
    certificate: WithdrawalCertificateBinding
  }): Promise<WithdrawalOperation> {
    const operation = await this.getOperation(input.operationId)
    operation.attempt = Math.max(operation.attempt, input.expectedAttempt + 1)
    operation.state = 'auth_pending'
    operation.auth_challenge = { uuid: `retry-${operation.attempt}`, data: `WMS517-RETRY-${operation.attempt}` }
    operation.documents = []
    operation.items = operation.items.map((item) => ({ ...item, status: 'not_withdrawn', error: null }))
    this.#operations.set(operation.operation_id, operation)
    return copyOperation(operation)
  }

  async submitAuthSignature(input: {
    operationId: string
    thumbprint: string
    signature: string
    challengeUuid: string
    expectedAttempt: number
  }): Promise<WithdrawalOperation> {
    const operation = await this.getOperation(input.operationId)
    const payloadBase64 = btoa(JSON.stringify({ action: 'DISTANCE', rows: this.#operationRows.get(input.operationId) }))
    operation.state = 'documents_pending_signature'
    operation.auth_challenge = null
    operation.documents = [{
      document_id: `40000000-0000-4000-8000-${input.operationId.slice(-12)}`,
      payload_base64: payloadBase64,
      payload_sha256: await sha256Base64Payload(payloadBase64),
      thumbprint: input.thumbprint,
    }]
    this.#operations.set(operation.operation_id, operation)
    return copyOperation(operation)
  }

  async submitDocumentSignatures(input: {
    operationId: string
    documents: WithdrawalDocumentSignatureInput[]
  }): Promise<WithdrawalOperation> {
    const operation = await this.getOperation(input.operationId)
    const selectedIds = this.#operationRows.get(input.operationId) ?? []
    const failedIds = new Set(this.#rows.filter((row) => selectedIds.includes(row.row_id) && row.submitFailure).map((row) => row.row_id))
    operation.items = operation.items.map((item) => failedIds.has(item.row_id)
      ? { ...item, status: 'error', error: { source: 'crpt', code: 'product_cost_missing', message: 'ЧЗ не принял документ: цена продажи не указана' } }
      : { ...item, status: 'withdrawn', error: null })
    operation.state = failedIds.size > 0 ? 'partial_failed' : 'succeeded'
    operation.documents = []
    this.#rows = this.#rows.map((row) => {
      const item = operation.items.find((candidate) => candidate.row_id === row.row_id)
      return item ? { ...row, status: item.status, error: item.error, operation_id: operation.operation_id } : row
    })
    this.#operations.set(operation.operation_id, operation)
    return copyOperation(operation)
  }
}

const DEMO_CERTIFICATE: CryptoProCertificate = {
  thumbprint: 'AABBCCDDEEFF00112233445566778899AABBCCDD',
  subject: 'CN=ИП Фадин Алексей Сергеевич, INN=771234567890',
  issuer: 'Тестовый УЦ КриптоПро',
  validFrom: '2026-06-18T00:00:00.000Z',
  validTo: '2027-06-18T00:00:00.000Z',
}

class AcceptanceSigningAdapter implements WithdrawalSigningAdapter {
  async checkReadiness() {
    return { pluginVersion: '2.0.15400', cspVersion: '5.0.13003' }
  }

  async listCertificates() {
    return [DEMO_CERTIFICATE]
  }

  async signAttachedAuthChallenge(input: { challengeData: string; certificateThumbprint: string }) {
    return { signatureBase64: btoa(`attached:${input.challengeData}`), certificateThumbprint: input.certificateThumbprint }
  }

  async signDetachedDocument(input: { payloadBase64: string; certificateThumbprint: string }) {
    return { signatureBase64: btoa(`detached:${input.payloadBase64}`), certificateThumbprint: input.certificateThumbprint }
  }
}

export function SellerKizWithdrawalAcceptanceScreen() {
  const api = useMemo(() => new AcceptanceWithdrawalApi(), [])
  const signingAdapter = useMemo(() => new AcceptanceSigningAdapter(), [])
  return (
    <Stack spacing={2}>
      <Alert severity="info"><strong>Интерактивный макет · данные демонстрационные.</strong> Запросы к WMS и Честному знаку эмулируются локально.</Alert>
      <SellerKizWithdrawalScreen
        token="acceptance-token"
        sellerId="acceptance-seller"
        api={api}
        signingAdapter={signingAdapter}
        pluginLoader={async () => undefined}
        routeBase=""
      />
    </Stack>
  )
}
