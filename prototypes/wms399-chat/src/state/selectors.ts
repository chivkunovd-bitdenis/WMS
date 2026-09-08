import type {
  Actor,
  Conversation,
  Message,
  Role,
  Visibility,
} from '../types'

export function visibleMessagesForActor(
  ordered: Message[],
  actor: Actor,
): Message[] {
  if (actor.role === 'seller') return ordered.filter((m) => m.visibility === 'shared')
  return ordered
}

export function conversationAccessible(conv: Conversation, actor: Actor): boolean {
  if (actor.role === 'ff_admin') return true
  if (actor.role === 'ff_operator') return conv.kind !== 'warehouse_internal' ? true : conv.warehouseId === actor.warehouseId
  return conv.sellerId === actor.sellerId && conv.kind !== 'warehouse_internal'
}

export function unreadCountForActor(conv: Conversation, msgs: Message[], actor: Actor) {
  const filtered = visibleMessagesForActor(msgs, actor).filter((m) => conv.unreadIds.includes(m.id))
  return filtered.length
}

export function mentionCountForActor(conv: Conversation, msgs: Message[], actor: Actor) {
  const filtered = visibleMessagesForActor(msgs, actor).filter((m) => conv.mentionIds.includes(m.id))
  return filtered.length
}

export function canWriteInternal(actor: Actor, conv: Conversation): boolean {
  if (actor.role === 'seller') return false
  if (conv.kind === 'warehouse_internal') return true
  return actor.role === 'ff_admin' || actor.role === 'ff_operator'
}

export function defaultVisibility(actor: Actor, conv: Conversation): Visibility {
  if (conv.kind === 'warehouse_internal') return 'internal'
  return 'shared'
}

export function readableRole(role: Role): string {
  if (role === 'ff_admin') return 'Админ ФФ'
  if (role === 'ff_operator') return 'Оператор ФФ'
  return 'Селлер'
}
