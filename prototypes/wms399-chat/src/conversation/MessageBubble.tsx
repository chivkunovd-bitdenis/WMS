import { useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  LinearProgress,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
  alpha,
} from '@mui/material'
import MoreVertIcon from '@mui/icons-material/MoreVertOutlined'
import ReplyIcon from '@mui/icons-material/ReplyOutlined'
import ForumIcon from '@mui/icons-material/ForumOutlined'
import FlagIcon from '@mui/icons-material/FlagOutlined'
import FlagFilledIcon from '@mui/icons-material/Flag'
import EmojiEmotionsIcon from '@mui/icons-material/EmojiEmotionsOutlined'
import LinkIcon from '@mui/icons-material/LinkOutlined'
import DescriptionIcon from '@mui/icons-material/DescriptionOutlined'
import CheckIcon from '@mui/icons-material/DoneOutlined'
import DoneAllIcon from '@mui/icons-material/DoneAllOutlined'
import ScheduleIcon from '@mui/icons-material/AccessTimeOutlined'
import ErrorIcon from '@mui/icons-material/ErrorOutlined'
import DeleteIcon from '@mui/icons-material/DeleteOutlineOutlined'
import EditIcon from '@mui/icons-material/EditOutlined'
import type { Conversation, Message, WmsDocument } from '../types'
import { useStore } from '../state/store'
import { PersonaAvatar } from '../common/PersonaAvatar'
import { fmtBytes, fmtTime } from '../utils/format'
import { docKindLabel, StatusChip } from '../common/StatusChip'
import { Row, Col } from '../common/Row'

const REACTIONS = ['👍', '👀', '🙏', '🔥', '❗', '✅']

export function MessageBubble({
  message,
  conversation,
  isThread,
  isFlash,
}: {
  message: Message
  conversation: Conversation
  isThread?: boolean
  isFlash?: boolean
}) {
  const { data, dispatch, dispatchData, currentActor, actorById, documentById, actions } = useStore()
  const author = actorById.get(message.authorId)
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null)
  const [emojiAnchor, setEmojiAnchor] = useState<HTMLElement | null>(null)

  const isOwn = message.authorId === currentActor.id
  const isInternal = message.visibility === 'internal'
  const isSellerReading = currentActor.role === 'seller'

  const doc = message.documentRef ? documentById.get(message.documentRef) : null
  const replyToMsg = message.replyToId ? data.messages.get(message.replyToId) : null
  const threadReplyCount = useMemo(() => {
    const ids = data.messagesByConversation.get(message.conversationId) ?? []
    return ids.reduce((n, id) => {
      const m = data.messages.get(id)
      return m && m.threadRootId === message.id ? n + 1 : n
    }, 0)
  }, [data.messages, data.messagesByConversation, message.id, message.conversationId])

  if (message.kind === 'system') {
    return (
      <Row justify="center" sx={{ my: 1.25 }}>
        <Chip
          size="small"
          label={message.systemPayload?.text ?? 'Событие'}
          sx={{
            bgcolor: 'info.light',
            color: 'info.main',
            fontWeight: 700,
            borderRadius: 999,
            border: '1px solid',
            borderColor: 'divider',
          }}
        />
      </Row>
    )
  }

  if (message.kind === 'deleted') {
    return (
      <Box sx={{ px: 1.5, py: 0.75, my: 0.75, opacity: 0.6, fontStyle: 'italic', color: 'text.secondary' }}>
        Сообщение удалено {fmtTime(message.deletedAt ?? message.createdAt)}
      </Box>
    )
  }

  const openThread = () => {
    dispatch({ type: 'open_thread', rootId: message.id })
  }

  const toggleReaction = (emoji: string) => {
    dispatchData({ type: 'toggle_reaction', messageId: message.id, emoji, actorId: currentActor.id })
    setEmojiAnchor(null)
  }

  const toggleFollowup = () => {
    dispatchData({ type: 'toggle_followup', messageId: message.id, actorId: currentActor.id, assigneeId: undefined })
  }

  const editable = isOwn && !isSellerReading
  const deletable = isOwn || currentActor.role === 'ff_admin'

  const bubbleBg = isInternal
    ? '#fff7ed'
    : isOwn
      ? 'primary.main'
      : 'background.paper'

  const bubbleColor = isInternal ? 'warning.main' : isOwn ? 'primary.contrastText' : 'text.primary'

  const alignItems = isOwn ? 'flex-end' : 'flex-start'

  const isDocCard = message.kind === 'document_card' && doc

  const followupOpen = message.followup && !message.followup.resolvedAt

  const readers = (message.readBy ?? []).filter((id) => id !== message.authorId)
  const participantsExceptAuthor = conversation.participantIds.filter((id) => id !== message.authorId)
  const allRead = readers.length >= participantsExceptAuthor.length && participantsExceptAuthor.length > 0

  const statusIcon =
    message.status === 'failed' ? (
      <ErrorIcon fontSize="inherit" color="error" />
    ) : message.status === 'sending' ? (
      <ScheduleIcon fontSize="inherit" color="disabled" />
    ) : allRead ? (
      <DoneAllIcon fontSize="inherit" sx={{ color: 'primary.light' }} />
    ) : (
      <CheckIcon fontSize="inherit" sx={{ color: 'text.secondary' }} />
    )

  return (
    <Box
      sx={{
        display: 'flex',
        gap: 1,
        my: 0.75,
        flexDirection: isOwn && !isThread ? 'row-reverse' : 'row',
        alignItems: 'flex-start',
        transition: 'background 250ms',
        bgcolor: isFlash ? (t) => alpha(t.palette.primary.main, 0.14) : 'transparent',
        borderRadius: 2,
        px: 0.5,
        py: 0.25,
      }}
      id={`msg-${message.id}`}
      data-testid={`message-${message.id}`}
    >
      {author ? <PersonaAvatar actor={author} size={34} /> : null}
      <Stack sx={{ maxWidth: '76%', minWidth: 0, alignItems }} spacing={0.5}>
        <Row align="baseline" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
          <Typography variant="caption" sx={{ fontWeight: 700, color: 'text.primary' }}>
            {author?.name ?? '?'}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {author?.title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            · {fmtTime(message.createdAt)}
          </Typography>
          {message.editedAt ? (
            <Typography variant="caption" color="text.secondary">
              · изменено
            </Typography>
          ) : null}
        </Row>

        <Box
          sx={{
            position: 'relative',
            bgcolor: bubbleBg,
            color: bubbleColor,
            border: '1px solid',
            borderColor: isInternal ? 'warning.main' : isOwn ? 'primary.dark' : 'divider',
            borderStyle: isInternal ? 'dashed' : 'solid',
            borderRadius: 2.5,
            px: 1.75,
            py: 1.25,
            minWidth: 120,
            boxShadow: isOwn ? '0 4px 10px rgba(76, 29, 149, 0.10)' : '0 1px 2px rgba(15,23,42,0.06)',
          }}
        >
          {isInternal ? (
            <Row align="center" spacing={0.75} sx={{ mb: 0.5 }}>
              <Chip
                size="small"
                label="Внутренняя заметка склада"
                sx={{
                  bgcolor: 'warning.main',
                  color: 'warning.contrastText',
                  height: 20,
                  fontWeight: 700,
                  fontSize: 11,
                }}
              />
              <Typography variant="caption" sx={{ color: 'warning.main' }}>
                Селлер этого не увидит
              </Typography>
            </Row>
          ) : null}
          {replyToMsg ? <ReplyPreview msg={replyToMsg} /> : null}
          {message.text ? (
            <Typography
              variant="body2"
              sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'inherit' }}
            >
              {renderMentions(message.text)}
            </Typography>
          ) : null}
          {isDocCard && doc ? <DocCard doc={doc} inOwn={isOwn} /> : null}
          {message.attachments && message.attachments.length > 0 ? (
            <AttachmentsGrid message={message} />
          ) : null}
          <Row align="center" spacing={1} sx={{ mt: 1 }}>
            {followupOpen ? (
              <Chip
                size="small"
                icon={<FlagFilledIcon sx={{ fontSize: 12 }} />}
                label="Требует ответа"
                sx={{ bgcolor: 'warning.main', color: 'warning.contrastText', fontWeight: 700, height: 22 }}
              />
            ) : null}
            {message.followup?.resolvedAt ? (
              <Chip
                size="small"
                label="Ответ дан"
                sx={{ bgcolor: 'success.light', color: 'success.dark', fontWeight: 700, height: 22 }}
              />
            ) : null}
            {threadReplyCount > 0 && !isThread ? (
              <Button
                size="small"
                variant="text"
                startIcon={<ForumIcon />}
                onClick={openThread}
                sx={{ color: isOwn ? 'primary.contrastText' : 'primary.main' }}
              >
                Обсуждение · {threadReplyCount}
              </Button>
            ) : null}
            <Box sx={{ flex: 1 }} />
            <Typography variant="caption" sx={{ color: isOwn ? 'primary.contrastText' : 'text.secondary', display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
              {isOwn ? statusIcon : null}
            </Typography>
          </Row>
        </Box>

        {message.reactions && message.reactions.length > 0 ? (
          <Stack direction="row" spacing={0.5}>
            {message.reactions.map((r) => (
              <Chip
                key={r.emoji}
                size="small"
                onClick={() => toggleReaction(r.emoji)}
                label={`${r.emoji} ${r.by.length}`}
                sx={{
                  height: 24,
                  bgcolor: r.by.includes(currentActor.id) ? 'primary.light' : 'action.hover',
                  color: r.by.includes(currentActor.id) ? 'primary.contrastText' : 'text.primary',
                  fontWeight: 700,
                }}
              />
            ))}
          </Stack>
        ) : null}

        <Stack direction="row" spacing={0.25} sx={{ mt: 0.25 }}>
          <Tooltip title="Реакция">
            <IconButton size="small" onClick={(e) => setEmojiAnchor(e.currentTarget)} aria-label="Реакция">
              <EmojiEmotionsIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {!isThread ? (
            <Tooltip title="Ответить в обсуждении">
              <IconButton size="small" onClick={openThread} aria-label="Обсуждение">
                <ForumIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : null}
          <Tooltip title={message.replyToId ? 'Ответить' : 'Ответить цитатой'}>
            <IconButton
              size="small"
              onClick={() => {
                dispatch({ type: 'set_draft', conversationId: conversation.id, patch: { replyToId: message.id } })
              }}
              aria-label="Ответить"
            >
              <ReplyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={followupOpen ? 'Снять «требует ответа»' : 'Пометить «требует ответа»'}>
            <IconButton size="small" onClick={toggleFollowup} aria-label="Требует ответа">
              {followupOpen ? <FlagFilledIcon fontSize="small" color="warning" /> : <FlagIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
          <Tooltip title="Скопировать ссылку-якорь на сообщение">
            <IconButton
              size="small"
              aria-label="Копировать ссылку"
              onClick={() => {
                const href = `#/c/${conversation.id}?msg=${message.id}`
                if (navigator?.clipboard) void navigator.clipboard.writeText(location.origin + location.pathname + href)
                dispatch({ type: 'set_flash', messageId: message.id })
                window.setTimeout(() => dispatch({ type: 'set_flash', messageId: null }), 1500)
              }}
            >
              <LinkIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <IconButton size="small" onClick={(e) => setMenuAnchor(e.currentTarget)} aria-label="Ещё">
            <MoreVertIcon fontSize="small" />
          </IconButton>
        </Stack>

        {message.status === 'failed' ? (
          <Alert
            severity="error"
            sx={{ mt: 0.5, p: 0.5, alignItems: 'center', width: 'auto' }}
            action={
              <Button
                size="small"
                onClick={() =>
                  dispatchData({
                    type: 'update_message',
                    id: message.id,
                    patch: { status: 'sent' },
                  })
                }
              >
                Повторить
              </Button>
            }
          >
            {message.attachments?.some((a) => a.uploadStatus === 'failed')
              ? 'Не отправлено: часть вложений не загрузилась.'
              : 'Не отправлено. Отправим при появлении сети.'}
          </Alert>
        ) : null}

        {isOwn && !isSellerReading && readers.length > 0 ? (
          <Typography variant="caption" color="text.secondary">
            Прочитали: {readers.length}/{participantsExceptAuthor.length}
          </Typography>
        ) : null}

        <Menu anchorEl={emojiAnchor} open={!!emojiAnchor} onClose={() => setEmojiAnchor(null)}>
          <Row spacing={0.5} sx={{ px: 1 }}>
            {REACTIONS.map((r) => (
              <IconButton key={r} size="small" onClick={() => toggleReaction(r)} aria-label={`Поставить реакцию ${r}`}>
                <span style={{ fontSize: 18 }}>{r}</span>
              </IconButton>
            ))}
          </Row>
        </Menu>

        <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)}>
          {editable ? (
            <MenuItem
              onClick={() => {
                setMenuAnchor(null)
                const next = window.prompt('Изменить текст сообщения', message.text ?? '')
                if (next != null && next !== message.text) {
                  dispatchData({
                    type: 'update_message',
                    id: message.id,
                    patch: { text: next, editedAt: new Date().toISOString() },
                  })
                }
              }}
            >
              <EditIcon fontSize="small" style={{ marginRight: 8 }} />
              Изменить
            </MenuItem>
          ) : null}
          {deletable ? (
            <MenuItem
              onClick={() => {
                setMenuAnchor(null)
                if (window.confirm('Удалить сообщение? Оно исчезнет у всех, останется тумба.')) {
                  dispatchData({ type: 'delete_message', id: message.id, actorId: currentActor.id })
                }
              }}
            >
              <DeleteIcon fontSize="small" style={{ marginRight: 8 }} />
              Удалить
            </MenuItem>
          ) : null}
          <MenuItem
            onClick={() => {
              setMenuAnchor(null)
              actions.openConversation(conversation.id, { flashMessageId: message.id, threadRootId: message.threadRootId })
            }}
          >
            <LinkIcon fontSize="small" style={{ marginRight: 8 }} />
            Открыть по якорю
          </MenuItem>
          {isInternal && !isSellerReading ? (
            <MenuItem
              onClick={() => {
                setMenuAnchor(null)
                dispatch({
                  type: 'set_draft',
                  conversationId: conversation.id,
                  patch: {
                    text: `Продублировано селлеру:\n${message.text ?? ''}`,
                    visibility: 'shared',
                  },
                })
              }}
            >
              <ReplyIcon fontSize="small" style={{ marginRight: 8 }} />
              Продублировать селлеру
            </MenuItem>
          ) : null}
        </Menu>
      </Stack>
    </Box>
  )
}

function ReplyPreview({ msg }: { msg: Message }) {
  const { actorById } = useStore()
  const author = actorById.get(msg.authorId)
  return (
    <Box
      sx={{
        borderLeft: '3px solid',
        borderColor: 'primary.light',
        pl: 1,
        mb: 0.75,
        opacity: 0.85,
      }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        {author?.name ?? '…'}
      </Typography>
      <Typography variant="body2" sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
        {msg.text || (msg.attachments?.length ? '📎 Вложение' : '[документ]')}
      </Typography>
    </Box>
  )
}

function renderMentions(text: string): React.ReactNode {
  const parts = text.split(/(@[\wа-яА-ЯёЁ.]+)/g)
  return parts.map((p, i) => {
    if (p.startsWith('@')) {
      return (
        <Box
          component="span"
          key={i}
          sx={{
            bgcolor: (t) => alpha(t.palette.primary.main, 0.14),
            color: 'primary.main',
            fontWeight: 700,
            px: 0.5,
            borderRadius: 0.75,
          }}
        >
          {p}
        </Box>
      )
    }
    return <span key={i}>{p}</span>
  })
}

function DocCard({ doc, inOwn }: { doc: WmsDocument; inOwn: boolean }) {
  const { dispatch, ui } = useStore()
  const outdated = ui.demo.documentOutdated
  const deleted = doc.deleted
  return (
    <Box
      sx={{
        mt: 1,
        p: 1.5,
        borderRadius: 2,
        bgcolor: inOwn ? 'primary.dark' : 'action.hover',
        color: inOwn ? 'primary.contrastText' : 'text.primary',
        border: '1px solid',
        borderColor: inOwn ? 'primary.light' : 'divider',
      }}
    >
      <Row align="flex-start" spacing={1.25}>
        <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: inOwn ? 'primary.light' : 'primary.main', color: 'primary.contrastText' }}>
          <DescriptionIcon fontSize="small" />
        </Box>
        <Stack sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800, color: 'inherit' }}>
            {docKindLabel(doc.kind)} · {doc.number}
          </Typography>
          <Typography variant="caption" sx={{ color: 'inherit', opacity: 0.85 }}>
            {doc.summary}
          </Typography>
          <Row spacing={0.5} sx={{ mt: 0.5 }}>
            <StatusChip status={doc.status} />
            <Chip size="small" label={`${doc.totalFact}/${doc.totalPlanned} шт`} sx={{ height: 22, bgcolor: 'background.paper', color: 'text.primary' }} />
          </Row>
          {outdated ? (
            <Alert severity="warning" sx={{ mt: 1 }} icon={false}>
              Документ обновлён после отправки. Откройте актуальную версию.
            </Alert>
          ) : deleted ? (
            <Alert severity="error" sx={{ mt: 1 }} icon={false}>
              Документ удалён. Ссылка недоступна.
            </Alert>
          ) : null}
        </Stack>
      </Row>
      <Row justify="flex-end" spacing={1} sx={{ mt: 1 }}>
        <Button
          size="small"
          variant="contained"
          disabled={deleted}
          onClick={() => dispatch({ type: 'open_document', documentId: doc.id })}
          sx={{
            bgcolor: inOwn ? 'primary.contrastText' : 'primary.main',
            color: inOwn ? 'primary.main' : 'primary.contrastText',
            '&:hover': { bgcolor: inOwn ? 'primary.contrastText' : 'primary.dark' },
          }}
        >
          Открыть документ
        </Button>
      </Row>
    </Box>
  )
}

function AttachmentsGrid({ message }: { message: Message }) {
  const { dispatch, dispatchData, actions } = useStore()
  const atts = message.attachments ?? []

  if (atts.length === 0) return null

  return (
    <Stack sx={{ mt: message.text ? 1 : 0 }} spacing={1}>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: atts.length === 1 ? '1fr' : atts.length === 2 ? '1fr 1fr' : 'repeat(3, 1fr)',
          gap: 0.75,
        }}
      >
        {atts.map((a) => {
          const inProgress = a.uploadStatus === 'uploading'
          const failed = a.uploadStatus === 'failed'
          if (a.kind === 'image') {
            return (
              <Box
                key={a.id}
                onClick={() =>
                  !failed && !inProgress
                    ? dispatch({ type: 'open_lightbox', payload: { messageId: message.id, attachmentId: a.id } })
                    : undefined
                }
                sx={{
                  position: 'relative',
                  aspectRatio: '4/3',
                  borderRadius: 2,
                  overflow: 'hidden',
                  cursor: inProgress || failed ? 'default' : 'zoom-in',
                  border: '1px solid',
                  borderColor: failed ? 'error.main' : 'divider',
                  bgcolor: 'background.paper',
                }}
              >
                {a.dataUri || a.blobUrl ? (
                  <img
                    src={a.dataUri ?? a.blobUrl}
                    alt={a.name}
                    loading="lazy"
                    style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', filter: inProgress ? 'blur(3px) grayscale(0.4)' : 'none' }}
                  />
                ) : (
                  <Box sx={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center', color: 'text.secondary' }}>
                    Нет предпросмотра
                  </Box>
                )}
                {inProgress ? (
                  <Box sx={{ position: 'absolute', inset: 0, bgcolor: 'rgba(15,23,42,0.35)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', p: 1 }}>
                    <LinearProgress variant="determinate" value={a.uploadProgress} sx={{ borderRadius: 1 }} />
                    <Typography variant="caption" sx={{ color: 'common.white', mt: 0.5 }}>
                      Загрузка… {a.uploadProgress}%
                    </Typography>
                  </Box>
                ) : null}
                {failed ? (
                  <Box sx={{ position: 'absolute', inset: 0, bgcolor: 'rgba(127,29,29,0.65)', color: 'common.white', display: 'grid', placeItems: 'center', p: 1, textAlign: 'center' }}>
                    <Col align="center" spacing={0.5}>
                      <ErrorIcon />
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>
                        {a.failReason ?? 'Не загрузилось'}
                      </Typography>
                      <Row spacing={0.5}>
                        <Button
                          size="small"
                          variant="contained"
                          color="warning"
                          onClick={(e) => {
                            e.stopPropagation()
                            actions.retryAttachment(message.id, a.id)
                          }}
                        >
                          Повторить
                        </Button>
                        <Button
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation()
                            const remaining = (message.attachments ?? []).filter((x) => x.id !== a.id)
                            dispatchData({
                              type: 'update_message',
                              id: message.id,
                              patch: { attachments: remaining.length ? remaining : undefined, status: 'sent' },
                            })
                          }}
                          sx={{ color: 'common.white' }}
                        >
                          Удалить
                        </Button>
                      </Row>
                    </Col>
                  </Box>
                ) : null}
              </Box>
            )
          }
          return (
            <Box
              key={a.id}
              sx={{
                borderRadius: 2,
                border: '1px solid',
                borderColor: failed ? 'error.main' : 'divider',
                p: 1.25,
                display: 'flex',
                gap: 1,
                alignItems: 'center',
                bgcolor: 'background.paper',
              }}
            >
              <Box sx={{ width: 36, height: 44, borderRadius: 1, bgcolor: 'action.hover', display: 'grid', placeItems: 'center', color: 'text.secondary', fontSize: 11, fontWeight: 700 }}>
                {a.mime.includes('pdf') ? 'PDF' : a.mime.includes('sheet') || a.name.endsWith('.xlsx') ? 'XLS' : a.mime.includes('csv') ? 'CSV' : 'ФАЙЛ'}
              </Box>
              <Stack sx={{ minWidth: 0, flex: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                  {a.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {fmtBytes(a.size)}
                  {inProgress ? ` · загрузка ${a.uploadProgress}%` : ''}
                  {failed ? ` · ${a.failReason ?? 'не загружено'}` : ''}
                </Typography>
                {inProgress ? <LinearProgress variant="determinate" value={a.uploadProgress} sx={{ mt: 0.5 }} /> : null}
              </Stack>
              {failed ? (
                <Button size="small" onClick={() => actions.retryAttachment(message.id, a.id)}>
                  Повторить
                </Button>
              ) : null}
            </Box>
          )
        })}
      </Box>
    </Stack>
  )
}
