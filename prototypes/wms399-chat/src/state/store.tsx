import { createContext, useCallback, useContext, useMemo, useReducer, useRef } from 'react'
import type { ReactNode } from 'react'
import type {
  Actor,
  Attachment,
  Conversation,
  DemoFlags,
  Message,
  MessageStatus,
  NotificationEntry,
  NotificationPrefs,
  Reaction,
  Role,
  Viewport,
  Visibility,
} from '../types'
import {
  actors as SEED_ACTORS,
  conversationsSeed,
  currentActorPresets,
  documents as SEED_DOCS,
  messagesSeed,
  notificationsSeed,
  sellers as SEED_SELLERS,
  warehouses as SEED_WAREHOUSES,
} from '../data/seed'

type UiState = {
  role: Role
  currentActorId: string
  viewport: Viewport
  selectedConversationId: string | null
  openThreadRootId: string | null
  openDocumentId: string | null
  openLightbox: { messageId: string; attachmentId: string } | null
  showParticipants: boolean
  showDemoMenu: boolean
  showDocumentPicker: boolean
  inboxFilter: {
    query: string
    kind: 'all' | 'mentions' | 'followup' | 'archived' | 'muted'
    sellerId: string | null
  }
  route: string
  drafts: Record<string, DraftState>
  demo: DemoFlags
  search: { query: string; sellerId: string | null; hasAttachment: boolean; hasDocument: boolean }
  notificationPrefs: NotificationPrefs
  flashMessageId: string | null
}

type DraftState = {
  text: string
  visibility: Visibility
  attachments: Attachment[]
  replyToId?: string
  documentRef?: string
  mentions: { actorId: string; offset: number; length: number }[]
}

const emptyDraft = (visibility: Visibility): DraftState => ({
  text: '',
  visibility,
  attachments: [],
  mentions: [],
})

const initialDemo: DemoFlags = {
  forceUploadFail: false,
  offline: false,
  documentOutdated: false,
  permissionDenied: false,
  slowNetwork: false,
}

const initialPrefs: NotificationPrefs = {
  pushEnabled: false,
  pushPermission: 'default',
  digest: 'off',
  mentionsOnly: false,
  perConversation: {},
}

const seedRoute = '#/inbox'

const initialState: UiState = {
  role: 'ff_operator',
  currentActorId: currentActorPresets.ff_operator!,
  viewport: typeof window !== 'undefined' && window.matchMedia('(max-width: 720px)').matches ? 'narrow' : 'desktop',
  selectedConversationId: 'conv_in2926',
  openThreadRootId: null,
  openDocumentId: null,
  openLightbox: null,
  showParticipants: false,
  showDemoMenu: false,
  showDocumentPicker: false,
  inboxFilter: { query: '', kind: 'all', sellerId: null },
  route: seedRoute,
  drafts: {},
  demo: { ...initialDemo },
  search: { query: '', sellerId: null, hasAttachment: false, hasDocument: false },
  notificationPrefs: { ...initialPrefs },
  flashMessageId: null,
}

type Action =
  | { type: 'set_role'; role: Role }
  | { type: 'set_actor'; actorId: string }
  | { type: 'set_viewport'; viewport: Viewport }
  | { type: 'select_conversation'; conversationId: string | null }
  | { type: 'open_thread'; rootId: string | null }
  | { type: 'open_document'; documentId: string | null }
  | { type: 'open_lightbox'; payload: UiState['openLightbox'] }
  | { type: 'toggle_participants'; open?: boolean }
  | { type: 'toggle_demo_menu'; open?: boolean }
  | { type: 'toggle_document_picker'; open?: boolean }
  | { type: 'set_inbox_filter'; patch: Partial<UiState['inboxFilter']> }
  | { type: 'set_draft'; conversationId: string; patch: Partial<DraftState> }
  | { type: 'clear_draft'; conversationId: string }
  | { type: 'set_route'; route: string }
  | { type: 'set_flash'; messageId: string | null }
  | { type: 'set_demo'; patch: Partial<DemoFlags> }
  | { type: 'set_search'; patch: Partial<UiState['search']> }
  | { type: 'set_prefs'; patch: Partial<NotificationPrefs> }

function reducer(state: UiState, action: Action): UiState {
  switch (action.type) {
    case 'set_role':
      return { ...state, role: action.role, currentActorId: currentActorPresets[action.role]! }
    case 'set_actor':
      return { ...state, currentActorId: action.actorId }
    case 'set_viewport':
      return { ...state, viewport: action.viewport }
    case 'select_conversation':
      return {
        ...state,
        selectedConversationId: action.conversationId,
        openThreadRootId: null,
      }
    case 'open_thread':
      return { ...state, openThreadRootId: action.rootId }
    case 'open_document':
      return { ...state, openDocumentId: action.documentId }
    case 'open_lightbox':
      return { ...state, openLightbox: action.payload }
    case 'toggle_participants':
      return { ...state, showParticipants: action.open ?? !state.showParticipants }
    case 'toggle_demo_menu':
      return { ...state, showDemoMenu: action.open ?? !state.showDemoMenu }
    case 'toggle_document_picker':
      return { ...state, showDocumentPicker: action.open ?? !state.showDocumentPicker }
    case 'set_inbox_filter':
      return { ...state, inboxFilter: { ...state.inboxFilter, ...action.patch } }
    case 'set_draft':
      return {
        ...state,
        drafts: {
          ...state.drafts,
          [action.conversationId]: {
            ...(state.drafts[action.conversationId] ?? emptyDraft('shared')),
            ...action.patch,
          },
        },
      }
    case 'clear_draft': {
      const next = { ...state.drafts }
      delete next[action.conversationId]
      return { ...state, drafts: next }
    }
    case 'set_route':
      return { ...state, route: action.route }
    case 'set_flash':
      return { ...state, flashMessageId: action.messageId }
    case 'set_demo':
      return { ...state, demo: { ...state.demo, ...action.patch } }
    case 'set_search':
      return { ...state, search: { ...state.search, ...action.patch } }
    case 'set_prefs':
      return { ...state, notificationPrefs: { ...state.notificationPrefs, ...action.patch } }
    default:
      return state
  }
}

type DataState = {
  conversations: Map<string, Conversation>
  messages: Map<string, Message>
  messagesByConversation: Map<string, string[]>
  notifications: NotificationEntry[]
}

type DataAction =
  | {
      type: 'add_message'
      message: Message
    }
  | { type: 'update_message'; id: string; patch: Partial<Message> }
  | { type: 'delete_message'; id: string; actorId: string }
  | { type: 'toggle_reaction'; messageId: string; emoji: string; actorId: string }
  | { type: 'toggle_followup'; messageId: string; actorId: string; assigneeId?: string }
  | { type: 'mark_read'; conversationId: string; actorId: string }
  | { type: 'pin'; conversationId: string; pinned: boolean }
  | { type: 'archive'; conversationId: string; archived: boolean }
  | { type: 'mute'; conversationId: string; muted: boolean }
  | { type: 'set_upload_status'; messageId: string; attachmentId: string; status: Attachment['uploadStatus']; progress: number; failReason?: string }
  | { type: 'add_notification'; notification: NotificationEntry }
  | { type: 'notif_read'; id: string }
  | { type: 'notif_read_all' }

function dataReducer(state: DataState, action: DataAction): DataState {
  switch (action.type) {
    case 'add_message': {
      const messages = new Map(state.messages)
      messages.set(action.message.id, action.message)
      const list = state.messagesByConversation.get(action.message.conversationId) ?? []
      const messagesByConversation = new Map(state.messagesByConversation)
      messagesByConversation.set(action.message.conversationId, [...list, action.message.id])
      const conversations = new Map(state.conversations)
      const conv = conversations.get(action.message.conversationId)
      if (conv) {
        conversations.set(action.message.conversationId, {
          ...conv,
          lastMessageId: action.message.id,
        })
      }
      return { ...state, messages, messagesByConversation, conversations }
    }
    case 'update_message': {
      const existing = state.messages.get(action.id)
      if (!existing) return state
      const messages = new Map(state.messages)
      messages.set(action.id, { ...existing, ...action.patch })
      return { ...state, messages }
    }
    case 'delete_message': {
      const existing = state.messages.get(action.id)
      if (!existing) return state
      const messages = new Map(state.messages)
      messages.set(action.id, {
        ...existing,
        kind: 'deleted',
        deletedAt: new Date().toISOString(),
        text: '',
        attachments: [],
        systemPayload: undefined,
      })
      return { ...state, messages }
    }
    case 'toggle_reaction': {
      const existing = state.messages.get(action.messageId)
      if (!existing) return state
      const rx: Reaction[] = existing.reactions ? existing.reactions.map((r) => ({ ...r, by: [...r.by] })) : []
      const found = rx.find((r) => r.emoji === action.emoji)
      if (!found) {
        rx.push({ emoji: action.emoji, by: [action.actorId] })
      } else if (found.by.includes(action.actorId)) {
        found.by = found.by.filter((x) => x !== action.actorId)
        if (found.by.length === 0) rx.splice(rx.indexOf(found), 1)
      } else {
        found.by.push(action.actorId)
      }
      const messages = new Map(state.messages)
      messages.set(action.messageId, { ...existing, reactions: rx })
      return { ...state, messages }
    }
    case 'toggle_followup': {
      const existing = state.messages.get(action.messageId)
      if (!existing) return state
      const nowIso = new Date().toISOString()
      const messages = new Map(state.messages)
      if (existing.followup && !existing.followup.resolvedAt) {
        messages.set(action.messageId, {
          ...existing,
          followup: { ...existing.followup, resolvedAt: nowIso, resolvedBy: action.actorId },
        })
      } else {
        messages.set(action.messageId, {
          ...existing,
          followup: { openedBy: action.actorId, openedAt: nowIso, assigneeId: action.assigneeId },
        })
      }
      return { ...state, messages }
    }
    case 'mark_read': {
      const conv = state.conversations.get(action.conversationId)
      if (!conv) return state
      const conversations = new Map(state.conversations)
      conversations.set(action.conversationId, { ...conv, unreadIds: [], mentionIds: [] })
      const messages = new Map(state.messages)
      const list = state.messagesByConversation.get(action.conversationId) ?? []
      for (const id of list) {
        const m = messages.get(id)
        if (!m) continue
        if (!m.readBy.includes(action.actorId)) {
          messages.set(id, { ...m, readBy: [...m.readBy, action.actorId] })
        }
      }
      return { ...state, conversations, messages }
    }
    case 'pin': {
      const conv = state.conversations.get(action.conversationId)
      if (!conv) return state
      const conversations = new Map(state.conversations)
      conversations.set(action.conversationId, { ...conv, pinned: action.pinned })
      return { ...state, conversations }
    }
    case 'archive': {
      const conv = state.conversations.get(action.conversationId)
      if (!conv) return state
      const conversations = new Map(state.conversations)
      conversations.set(action.conversationId, { ...conv, archived: action.archived })
      return { ...state, conversations }
    }
    case 'mute': {
      const conv = state.conversations.get(action.conversationId)
      if (!conv) return state
      const conversations = new Map(state.conversations)
      conversations.set(action.conversationId, { ...conv, muted: action.muted })
      return { ...state, conversations }
    }
    case 'set_upload_status': {
      const msg = state.messages.get(action.messageId)
      if (!msg || !msg.attachments) return state
      const attachments = msg.attachments.map((att) =>
        att.id === action.attachmentId
          ? {
              ...att,
              uploadStatus: action.status,
              uploadProgress: action.progress,
              failReason: action.failReason,
            }
          : att,
      )
      const nextStatus: MessageStatus = attachments.every((a) => a.uploadStatus === 'done')
        ? 'sent'
        : attachments.some((a) => a.uploadStatus === 'failed')
          ? 'failed'
          : 'sending'
      const messages = new Map(state.messages)
      messages.set(action.messageId, { ...msg, attachments, status: nextStatus })
      return { ...state, messages }
    }
    case 'add_notification':
      return { ...state, notifications: [action.notification, ...state.notifications] }
    case 'notif_read':
      return {
        ...state,
        notifications: state.notifications.map((n) => (n.id === action.id ? { ...n, read: true } : n)),
      }
    case 'notif_read_all':
      return { ...state, notifications: state.notifications.map((n) => ({ ...n, read: true })) }
    default:
      return state
  }
}

function buildInitialData(): DataState {
  const conversations = new Map<string, Conversation>()
  for (const c of conversationsSeed) conversations.set(c.id, c)
  const messages = new Map<string, Message>()
  const messagesByConversation = new Map<string, string[]>()
  const sortedSeed = [...messagesSeed].sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  for (const m of sortedSeed) {
    messages.set(m.id, m)
    const arr = messagesByConversation.get(m.conversationId) ?? []
    arr.push(m.id)
    messagesByConversation.set(m.conversationId, arr)
  }
  return { conversations, messages, messagesByConversation, notifications: [...notificationsSeed] }
}

type StoreShape = {
  ui: UiState
  data: DataState
  currentActor: Actor
  actorById: Map<string, Actor>
  sellerById: Map<string, (typeof SEED_SELLERS)[number]>
  warehouseById: Map<string, (typeof SEED_WAREHOUSES)[number]>
  documentById: Map<string, (typeof SEED_DOCS)[number]>
  dispatch: (a: Action) => void
  dispatchData: (a: DataAction) => void
  navigate: (route: string) => void
  actions: ReturnType<typeof buildActions>
}

const Ctx = createContext<StoreShape | null>(null)

function buildActions(deps: {
  dispatch: (a: Action) => void
  dispatchData: (a: DataAction) => void
  getState: () => { ui: UiState; data: DataState; currentActor: Actor }
  navigate: (route: string) => void
}) {
  const { dispatch, dispatchData, getState, navigate } = deps

  const sendMessage = (
    conversationId: string,
    payload: {
      text: string
      visibility: Visibility
      attachments: Attachment[]
      replyToId?: string
      threadRootId?: string
      documentRef?: string
      mentions?: Message['mentions']
    },
  ) => {
    const { currentActor, ui, data } = getState()
    const now = new Date().toISOString()
    const clientId = `local_${Math.random().toString(36).slice(2, 10)}`
    const isDocCard = !!payload.documentRef && !payload.attachments.length && !payload.text.trim()
    const willFailUpload = ui.demo.forceUploadFail && payload.attachments.length > 0
    const offline = ui.demo.offline

    const status: MessageStatus = offline
      ? 'failed'
      : payload.attachments.length > 0
        ? 'sending'
        : 'sent'
    const msg: Message = {
      id: `msg_${clientId}`,
      conversationId,
      authorId: currentActor.id,
      createdAt: now,
      kind: isDocCard ? 'document_card' : 'text',
      visibility: payload.visibility,
      text: payload.text.trim(),
      attachments: payload.attachments.length
        ? payload.attachments.map((a) => ({ ...a, uploadStatus: offline ? 'failed' : a.uploadStatus, failReason: offline ? 'Нет сети' : a.failReason }))
        : undefined,
      replyToId: payload.replyToId,
      threadRootId: payload.threadRootId,
      documentRef: payload.documentRef,
      mentions: payload.mentions,
      status,
      readBy: [currentActor.id],
      clientMessageId: clientId,
    }
    dispatchData({ type: 'add_message', message: msg })

    if (!offline && payload.attachments.length > 0) {
      let done = 0
      const total = payload.attachments.length
      for (const att of payload.attachments) {
        const shouldFail = willFailUpload
        const steps = ui.demo.slowNetwork ? 6 : 3
        let step = 0
        const interval = window.setInterval(() => {
          step += 1
          const pct = Math.min(100, Math.round((step / steps) * 100))
          if (step >= steps) {
            window.clearInterval(interval)
            if (shouldFail) {
              dispatchData({
                type: 'set_upload_status',
                messageId: msg.id,
                attachmentId: att.id,
                status: 'failed',
                progress: pct,
                failReason: 'Тестовый сбой антивируса',
              })
            } else {
              dispatchData({
                type: 'set_upload_status',
                messageId: msg.id,
                attachmentId: att.id,
                status: 'done',
                progress: 100,
              })
              done += 1
              if (done === total) {
                dispatchData({ type: 'update_message', id: msg.id, patch: { status: 'sent' } })
              }
            }
          } else {
            dispatchData({
              type: 'set_upload_status',
              messageId: msg.id,
              attachmentId: att.id,
              status: 'uploading',
              progress: pct,
            })
          }
        }, 220)
      }
    }

    if (payload.mentions && !offline) {
      for (const m of payload.mentions) {
        dispatchData({
          type: 'add_notification',
          notification: {
            id: `ntf_${Math.random().toString(36).slice(2, 8)}`,
            kind: 'mention',
            createdAt: now,
            conversationId,
            messageId: msg.id,
            actorId: currentActor.id,
            preview: payload.text.slice(0, 80),
            read: false,
          },
        })
        void data
        void m
      }
    }

    dispatch({ type: 'clear_draft', conversationId })
    return msg.id
  }

  const retryAttachment = (messageId: string, attachmentId: string) => {
    const { data } = getState()
    const msg = data.messages.get(messageId)
    if (!msg) return
    dispatchData({
      type: 'set_upload_status',
      messageId,
      attachmentId,
      status: 'uploading',
      progress: 0,
    })
    let step = 0
    const interval = window.setInterval(() => {
      step += 1
      if (step >= 4) {
        window.clearInterval(interval)
        dispatchData({
          type: 'set_upload_status',
          messageId,
          attachmentId,
          status: 'done',
          progress: 100,
        })
        const later = getState().data.messages.get(messageId)
        if (later?.attachments?.every((a) => a.uploadStatus === 'done')) {
          dispatchData({ type: 'update_message', id: messageId, patch: { status: 'sent' } })
        }
      } else {
        dispatchData({
          type: 'set_upload_status',
          messageId,
          attachmentId,
          status: 'uploading',
          progress: Math.round((step / 4) * 100),
        })
      }
    }, 300)
  }

  const openConversation = (conversationId: string, opts?: { flashMessageId?: string; threadRootId?: string }) => {
    dispatch({ type: 'select_conversation', conversationId })
    if (opts?.threadRootId) dispatch({ type: 'open_thread', rootId: opts.threadRootId })
    if (opts?.flashMessageId) {
      dispatch({ type: 'set_flash', messageId: opts.flashMessageId })
    }
    const state = getState()
    dispatchData({ type: 'mark_read', conversationId, actorId: state.currentActor.id })
    navigate(`#/c/${conversationId}${opts?.threadRootId ? `/t/${opts.threadRootId}` : ''}${opts?.flashMessageId ? `?msg=${opts.flashMessageId}` : ''}`)
  }

  return {
    sendMessage,
    retryAttachment,
    openConversation,
  }
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [ui, dispatch] = useReducer(reducer, initialState)
  const [data, dispatchData] = useReducer(dataReducer, undefined, buildInitialData)

  const actorById = useMemo(() => new Map(SEED_ACTORS.map((a) => [a.id, a])), [])
  const sellerById = useMemo(() => new Map(SEED_SELLERS.map((s) => [s.id, s])), [])
  const warehouseById = useMemo(() => new Map(SEED_WAREHOUSES.map((w) => [w.id, w])), [])
  const documentById = useMemo(() => new Map(SEED_DOCS.map((d) => [d.id, d])), [])

  const stateRef = useRef({ ui, data, currentActor: actorById.get(ui.currentActorId)! })
  stateRef.current = { ui, data, currentActor: actorById.get(ui.currentActorId)! }

  const navigate = useCallback((route: string) => {
    if (typeof window !== 'undefined' && window.location.hash !== route) {
      window.history.pushState({}, '', route)
    }
    dispatch({ type: 'set_route', route })
  }, [])

  const actions = useMemo(
    () =>
      buildActions({
        dispatch,
        dispatchData,
        getState: () => stateRef.current,
        navigate,
      }),
    [navigate],
  )

  const value: StoreShape = {
    ui,
    data,
    currentActor: actorById.get(ui.currentActorId)!,
    actorById,
    sellerById,
    warehouseById,
    documentById,
    dispatch,
    dispatchData,
    navigate,
    actions,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error('ChatProvider missing')
  return v
}
