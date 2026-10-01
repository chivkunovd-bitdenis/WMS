export type RequestType = 'bug' | 'improvement'
export type RequestStatus = 'review' | 'queued' | 'in_progress' | 'completed'
export type RequestRecord = {
  id: string
  type: RequestType
  title: string
  description: string | null
  screen: string | null
  problem: string | null
  proposal: string | null
  status: RequestStatus
  created_at: string
  updated_at: string
}
export type RequestIdentity = {
  id: string
  tenant_id: string
  active_seller_id?: string | null
  seller_id?: string | null
}
export type RequestPayload = {
  idempotency_key: string
  type: RequestType
  description?: string
  screen?: string
  problem?: string
  proposal?: string
  page_url: string
}
export type Draft = {
  type: RequestType
  description: string
  screen: string
  problem: string
  proposal: string
  key: string
  // Keep the first submitted body across edits/reloads: it can safely recover a lost response.
  attempt?: RequestPayload
}
export const statusLabels: Record<RequestStatus, string> = {
  review: 'На рассмотрении', queued: 'В очереди', in_progress: 'В работе', completed: 'Готово',
}
export const typeLabels: Record<RequestType, string> = { bug: 'Ошибка', improvement: 'Улучшение / доработка' }
export function draftStorageKey(me: RequestIdentity): string {
  return `wms.developer-request.v1:${JSON.stringify([me.tenant_id, me.id, me.active_seller_id ?? me.seller_id ?? null])}`
}
export function emptyDraft(): Draft {
  return { type: 'bug', description: '', screen: '', problem: '', proposal: '', key: crypto.randomUUID() }
}
export function readDraft(key: string): Draft {
  const raw = localStorage.getItem(key)
  if (!raw) return emptyDraft()
  const value = JSON.parse(raw) as Draft
  if (!value || !['bug', 'improvement'].includes(value.type) ||
    !['description', 'screen', 'problem', 'proposal', 'key'].every((field) => typeof value[field as keyof Draft] === 'string')) return emptyDraft()
  return value
}
export function requestPayload(draft: Draft, pathname: string): RequestPayload {
  return {
    idempotency_key: draft.key, type: draft.type,
    ...(draft.type === 'bug' ? { description: draft.description.trim() } : {
      screen: draft.screen.trim(), problem: draft.problem.trim(), proposal: draft.proposal.trim(),
    }),
    // A retry on another screen must not change the fingerprint of the original request.
    page_url: draft.attempt?.page_url ?? pathname.split(/[?#]/)[0],
  }
}
export function validateDraft(draft: Draft): Partial<Record<'description' | 'screen' | 'problem' | 'proposal', string>> {
  const fields = draft.type === 'bug' ? ['description'] as const : ['screen', 'problem', 'proposal'] as const
  return Object.fromEntries(fields.filter((field) => !draft[field].trim()).map((field) => [field, 'Заполните поле']))
}
