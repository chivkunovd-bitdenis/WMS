import { Box, Chip, Stack, Typography, alpha } from '@mui/material'
import FlagIcon from '@mui/icons-material/FlagOutlined'
import PushPinIcon from '@mui/icons-material/PushPinOutlined'
import VolumeOffIcon from '@mui/icons-material/VolumeOffOutlined'
import LockIcon from '@mui/icons-material/LockOutlined'
import { useStore } from '../state/store'
import type { Conversation } from '../types'
import { PersonaAvatar } from '../common/PersonaAvatar'
import { SellerAvatar } from '../common/SellerAvatar'
import { Row } from '../common/Row'
import { visibleMessagesForActor } from '../state/selectors'
import { fmtTime } from '../utils/format'

const KIND_LABEL: Record<Conversation['kind'], string> = {
  seller_general: 'Общий',
  inbound: 'Приёмка',
  mp_outbound: 'Отгрузка',
  fbs_batch: 'FBS',
  return: 'Возврат',
  warehouse_internal: 'Внутр. склад',
}

export function ConversationRow({ conversation }: { conversation: Conversation }) {
  const { actions, ui, data, currentActor, sellerById, warehouseById } = useStore()

  const seller = conversation.sellerId ? sellerById.get(conversation.sellerId) : null
  const warehouse = conversation.warehouseId ? warehouseById.get(conversation.warehouseId) : null

  const isSelected = ui.selectedConversationId === conversation.id
  const messages = data.messagesByConversation.get(conversation.id) ?? []
  const visibleMsgs = visibleMessagesForActor(
    messages
      .map((id) => data.messages.get(id))
      .filter((m): m is NonNullable<typeof m> => Boolean(m)),
    currentActor,
  )
  const visibleUnread = visibleMsgs.filter((m) => conversation.unreadIds.includes(m.id)).length
  const mentions = visibleMsgs.filter((m) => conversation.mentionIds.includes(m.id)).length
  const lastVisible = visibleMsgs[visibleMsgs.length - 1] ?? null

  const previewText = lastVisible
    ? (lastVisible.text || (lastVisible.attachments?.length ? '📎 Вложение' : lastVisible.systemPayload?.text || '[документ]'))
    : 'Ещё нет сообщений'

  const isInternalPreview = lastVisible?.visibility === 'internal' && currentActor.role !== 'seller'

  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={() => actions.openConversation(conversation.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') actions.openConversation(conversation.id)
      }}
      sx={(t) => ({
        px: 2,
        py: 1.4,
        cursor: 'pointer',
        display: 'flex',
        gap: 1.25,
        alignItems: 'flex-start',
        bgcolor: isSelected ? alpha(t.palette.primary.main, 0.08) : 'transparent',
        borderLeft: '3px solid',
        borderColor: isSelected ? 'primary.main' : 'transparent',
        transition: 'background 120ms',
        '&:hover': { bgcolor: alpha(t.palette.primary.main, 0.05) },
        outline: 'none',
        '&:focus-visible': { boxShadow: `inset 0 0 0 2px ${t.palette.primary.main}` },
      })}
      aria-label={`${conversation.title}. Непрочитанных: ${visibleUnread}.`}
      data-testid={`inbox-row-${conversation.id}`}
    >
      {conversation.kind === 'warehouse_internal' ? (
        <Box sx={{ width: 40, height: 40, borderRadius: 2, bgcolor: 'grey.900', color: 'grey.100', display: 'grid', placeItems: 'center' }}>
          <LockIcon fontSize="small" />
        </Box>
      ) : seller ? (
        <SellerAvatar seller={seller} size={40} />
      ) : (
        <PersonaAvatar actor={{ id: 'x', name: '?', short: '?', role: 'ff_admin', color: '#334155' }} size={40} />
      )}
      <Stack sx={{ flex: 1, minWidth: 0 }} spacing={0.25}>
        <Row align="center" spacing={0.75}>
          {conversation.pinned ? <PushPinIcon sx={{ fontSize: 14, color: 'primary.main' }} /> : null}
          <Typography variant="body2" sx={{ fontWeight: 700, flex: 1, minWidth: 0 }} noWrap>
            {conversation.title}
          </Typography>
          {lastVisible ? (
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
              {fmtTime(lastVisible.createdAt)}
            </Typography>
          ) : null}
        </Row>
        <Row align="center" spacing={0.5}>
          <Chip
            size="small"
            label={KIND_LABEL[conversation.kind]}
            sx={{ height: 18, fontSize: 10, fontWeight: 700, bgcolor: 'action.selected', color: 'text.secondary' }}
          />
          {conversation.followupOpen ? (
            <Chip
              size="small"
              icon={<FlagIcon sx={{ fontSize: 12 }} />}
              label="ответить"
              sx={{ height: 18, fontSize: 10, fontWeight: 700, bgcolor: 'warning.light', color: 'warning.main' }}
            />
          ) : null}
          {conversation.muted ? <VolumeOffIcon sx={{ fontSize: 14, color: 'text.secondary' }} /> : null}
          <Typography variant="caption" color="text.secondary" noWrap sx={{ flex: 1 }}>
            {warehouse?.name}
          </Typography>
        </Row>
        <Row align="flex-start" spacing={1}>
          <Typography
            variant="body2"
            sx={{
              flex: 1,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              color: isInternalPreview ? 'warning.main' : 'text.secondary',
              fontStyle: isInternalPreview ? 'italic' : 'normal',
            }}
          >
            {isInternalPreview ? 'внутр. ' : ''}
            {previewText}
          </Typography>
          <Stack direction="row" spacing={0.5}>
            {mentions > 0 ? (
              <Chip
                size="small"
                label={`@${mentions}`}
                sx={{ height: 20, fontSize: 11, bgcolor: 'primary.main', color: 'primary.contrastText', fontWeight: 700 }}
              />
            ) : null}
            {visibleUnread > 0 ? (
              <Chip
                size="small"
                label={visibleUnread}
                sx={{ height: 20, minWidth: 24, fontSize: 11, bgcolor: 'primary.dark', color: 'primary.contrastText', fontWeight: 700 }}
              />
            ) : null}
          </Stack>
        </Row>
      </Stack>
    </Box>
  )
}
