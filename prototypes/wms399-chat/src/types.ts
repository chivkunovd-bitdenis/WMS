export type Role = 'ff_admin' | 'ff_operator' | 'seller'

export type Viewport = 'desktop' | 'narrow'

export type Actor = {
  id: string
  name: string
  short: string
  role: Role
  color: string
  sellerId?: string
  warehouseId?: string
  title?: string
}

export type Seller = {
  id: string
  brand: string
  short: string
  color: string
  contact: string
}

export type Warehouse = {
  id: string
  name: string
  code: string
  city: string
}

export type DocumentKind = 'inbound' | 'mp_outbound' | 'fbs_batch' | 'return'

export type DocumentStatus =
  | 'draft'
  | 'submitted'
  | 'in_progress'
  | 'confirmed'
  | 'shipped'
  | 'closed'
  | 'discrepancy'

export type DocLine = {
  sku: string
  name: string
  planned: number
  fact?: number
  note?: string
}

export type WmsDocument = {
  id: string
  number: string
  kind: DocumentKind
  status: DocumentStatus
  sellerId: string
  warehouseId: string
  updatedAt: string
  createdAt: string
  lines: DocLine[]
  summary: string
  totalPlanned: number
  totalFact: number
  timeline: DocumentEvent[]
  deleted?: boolean
  outdated?: boolean
}

export type DocumentEvent = {
  id: string
  at: string
  by: string
  text: string
  linkedMessageId?: string
}

export type AttachmentKind = 'image' | 'file'

export type Attachment = {
  id: string
  name: string
  size: number
  mime: string
  kind: AttachmentKind
  width?: number
  height?: number
  dataUri?: string
  uploadStatus: 'uploading' | 'done' | 'failed'
  uploadProgress: number
  failReason?: string
  blobUrl?: string
}

export type Reaction = {
  emoji: string
  by: string[]
}

export type MessageKind = 'text' | 'system' | 'document_card' | 'deleted'

export type Visibility = 'internal' | 'shared'

export type MessageStatus = 'sending' | 'sent' | 'failed'

export type Mention = {
  actorId: string
  offset: number
  length: number
  channel?: boolean
}

export type Message = {
  id: string
  conversationId: string
  authorId: string
  createdAt: string
  editedAt?: string
  deletedAt?: string
  kind: MessageKind
  visibility: Visibility
  text?: string
  attachments?: Attachment[]
  reactions?: Reaction[]
  mentions?: Mention[]
  replyToId?: string
  threadRootId?: string
  documentRef?: string
  followup?: {
    openedBy: string
    assigneeId?: string
    openedAt: string
    resolvedAt?: string
    resolvedBy?: string
  }
  status: MessageStatus
  readBy: string[]
  clientMessageId?: string
  systemPayload?: {
    icon: 'shipped' | 'status' | 'thread_closed' | 'document_updated' | 'joined' | 'left'
    text: string
  }
  threadReplyCount?: number
}

export type ConversationKind =
  | 'seller_general'
  | 'inbound'
  | 'mp_outbound'
  | 'fbs_batch'
  | 'return'
  | 'warehouse_internal'

export type Conversation = {
  id: string
  kind: ConversationKind
  sellerId?: string
  warehouseId?: string
  documentId?: string
  title: string
  subtitle?: string
  pinned: boolean
  archived: boolean
  muted: boolean
  participantIds: string[]
  lastMessageId?: string
  unreadIds: string[]
  mentionIds: string[]
  followupOpen: boolean
}

export type NotificationKind =
  | 'mention'
  | 'shared_message'
  | 'followup_assigned'
  | 'thread_reply'
  | 'system'

export type NotificationEntry = {
  id: string
  kind: NotificationKind
  createdAt: string
  conversationId: string
  messageId: string
  actorId: string
  preview: string
  read: boolean
}

export type NotificationPrefs = {
  pushEnabled: boolean
  pushPermission: 'granted' | 'denied' | 'default'
  digest: 'off' | 'hourly' | 'daily'
  mentionsOnly: boolean
  perConversation: Record<string, { muted: boolean }>
}

export type DemoFlags = {
  forceUploadFail: boolean
  offline: boolean
  documentOutdated: boolean
  documentDeleted: boolean
  permissionDenied: boolean
  slowNetwork: boolean
  loading: boolean
}
