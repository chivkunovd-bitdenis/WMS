import { useMemo, useState } from 'react'
import { Alert, Box, Divider, IconButton, Stack, Tab, Tabs, Typography, alpha } from '@mui/material'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeftOutlined'
import PushPinIcon from '@mui/icons-material/PushPinOutlined'
import PushPinOnIcon from '@mui/icons-material/PushPin'
import VolumeOffIcon from '@mui/icons-material/VolumeOffOutlined'
import VolumeUpIcon from '@mui/icons-material/VolumeUpOutlined'
import ArchiveIcon from '@mui/icons-material/ArchiveOutlined'
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined'
import DescriptionIcon from '@mui/icons-material/DescriptionOutlined'
import ForumIcon from '@mui/icons-material/ForumOutlined'
import { useStore } from '../state/store'
import { EmptyState } from '../common/EmptyState'
import { MessageList } from './MessageList'
import { Composer } from './Composer'
import { ContextPanel } from './ContextPanel'
import { ThreadPanel } from './ThreadPanel'
import { conversationAccessible } from '../state/selectors'
import { SellerAvatar } from '../common/SellerAvatar'
import { docKindLabel } from '../common/StatusChip'
import type { Conversation } from '../types'

const KIND_LABEL: Record<Conversation['kind'], string> = {
  seller_general: 'Общий канал',
  inbound: 'Приёмка',
  mp_outbound: 'Отгрузка на МП',
  fbs_batch: 'FBS-партия',
  return: 'Возврат',
  warehouse_internal: 'Внутренний канал склада',
}

export function ConversationScreen() {
  const { ui, data, currentActor, sellerById, warehouseById, documentById, dispatch, dispatchData, navigate } = useStore()
  const [rightTab, setRightTab] = useState<'context' | 'thread'>('context')

  const conv = ui.selectedConversationId ? data.conversations.get(ui.selectedConversationId) : null

  const hasAccess = conv ? conversationAccessible(conv, currentActor) : false
  const permBlocked = ui.demo.permissionDenied
  const doc = conv?.documentId ? documentById.get(conv.documentId) : null

  const seller = conv?.sellerId ? sellerById.get(conv.sellerId) : null
  const warehouse = conv?.warehouseId ? warehouseById.get(conv.warehouseId) : null

  const orderedIds = useMemo(() => {
    if (!conv) return [] as string[]
    return data.messagesByConversation.get(conv.id) ?? []
  }, [conv, data.messagesByConversation])

  const showThread = ui.openThreadRootId != null

  if (!conv) {
    return (
      <Box sx={{ flex: 1, display: 'flex' }}>
        <EmptyState
          title="Выберите канал"
          description="Слева — список каналов вашего тенанта. Каналы под документы появляются в момент первого сообщения."
        />
      </Box>
    )
  }

  if (!hasAccess || permBlocked) {
    return (
      <Box sx={{ flex: 1, display: 'flex' }}>
        <EmptyState
          title="Нет доступа к каналу"
          description={
            permBlocked
              ? 'В демо включен режим «нет доступа»: сервер отдал 403 на этот канал.'
              : 'Этот канал не входит в область видимости вашей роли. Обратитесь к админу ФФ.'
          }
        />
      </Box>
    )
  }

  const goBack = () => {
    dispatch({ type: 'select_conversation', conversationId: null })
    navigate('#/inbox')
  }

  const togglePin = () => dispatchData({ type: 'pin', conversationId: conv.id, pinned: !conv.pinned })
  const toggleMute = () => dispatchData({ type: 'mute', conversationId: conv.id, muted: !conv.muted })
  const toggleArchive = () => dispatchData({ type: 'archive', conversationId: conv.id, archived: !conv.archived })

  return (
    <Box sx={{ flex: 1, display: 'flex', minWidth: 0 }} data-testid="conversation-screen">
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, bgcolor: 'background.default' }}>
        <Box
          sx={(t) => ({
            px: { xs: 2, md: 3 },
            py: 1.5,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
            display: 'flex',
            gap: 1.5,
            alignItems: 'center',
            position: 'sticky',
            top: 0,
            zIndex: t.zIndex.appBar - 1,
          })}
        >
          {ui.viewport === 'narrow' ? (
            <IconButton onClick={goBack} aria-label="К инбоксу">
              <ChevronLeftIcon />
            </IconButton>
          ) : null}
          {conv.kind === 'warehouse_internal' ? (
            <Box sx={{ width: 40, height: 40, borderRadius: 2, bgcolor: 'grey.900', color: 'grey.100', display: 'grid', placeItems: 'center' }}>
              <ForumIcon fontSize="small" />
            </Box>
          ) : seller ? (
            <SellerAvatar seller={seller} size={40} />
          ) : null}
          <Stack sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }} noWrap>
              {conv.title}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {KIND_LABEL[conv.kind]}
              {warehouse ? ` · ${warehouse.name}` : ''}
              {doc ? ` · ${docKindLabel(doc.kind)} ${doc.number}` : ''}
              {conv.participantIds.length ? ` · ${conv.participantIds.length} участников` : ''}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={0.5}>
            <IconButton size="small" aria-label={conv.pinned ? 'Открепить' : 'Закрепить'} onClick={togglePin}>
              {conv.pinned ? <PushPinOnIcon fontSize="small" color="primary" /> : <PushPinIcon fontSize="small" />}
            </IconButton>
            <IconButton size="small" aria-label={conv.muted ? 'Включить звук' : 'Заглушить'} onClick={toggleMute}>
              {conv.muted ? <VolumeOffIcon fontSize="small" color="warning" /> : <VolumeUpIcon fontSize="small" />}
            </IconButton>
            <IconButton size="small" aria-label={conv.archived ? 'Разархивировать' : 'В архив'} onClick={toggleArchive}>
              <ArchiveIcon fontSize="small" color={conv.archived ? 'warning' : 'inherit'} />
            </IconButton>
            <IconButton size="small" aria-label="Участники" onClick={() => dispatch({ type: 'toggle_participants', open: true })}>
              <PeopleIcon fontSize="small" />
            </IconButton>
            {doc ? (
              <IconButton size="small" aria-label="Документ" onClick={() => dispatch({ type: 'open_document', documentId: doc.id })}>
                <DescriptionIcon fontSize="small" />
              </IconButton>
            ) : null}
          </Stack>
        </Box>

        {conv.archived ? (
          <Alert severity="info" sx={{ borderRadius: 0 }} variant="outlined">
            Канал в архиве. Только чтение. Разархивируйте, чтобы отправлять сообщения.
          </Alert>
        ) : null}

        <Divider />
        <Box sx={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', px: { xs: 1.5, md: 3 }, py: 2, bgcolor: (t) => alpha(t.palette.primary.main, 0.03) }}>
              <MessageList conversation={conv} orderedIds={orderedIds} />
            </Box>
            {!conv.archived ? <Composer conversation={conv} /> : null}
          </Box>
        </Box>
      </Box>
      {ui.viewport === 'desktop' ? (
        <Box sx={{ width: 380, borderLeft: '1px solid', borderColor: 'divider', bgcolor: 'background.paper', display: 'flex', flexDirection: 'column' }}>
          <Tabs
            value={showThread ? 'thread' : rightTab}
            onChange={(_, v) => {
              if (v === 'thread') return
              setRightTab(v)
            }}
            sx={{ borderBottom: '1px solid', borderColor: 'divider', px: 1.5 }}
          >
            <Tab value="context" label="Контекст" />
            <Tab value="thread" label="Обсуждение" disabled={!showThread} />
          </Tabs>
          <Box sx={{ flex: 1, overflow: 'auto' }}>
            {showThread ? <ThreadPanel conversation={conv} /> : <ContextPanel conversation={conv} />}
          </Box>
        </Box>
      ) : null}
    </Box>
  )
}
