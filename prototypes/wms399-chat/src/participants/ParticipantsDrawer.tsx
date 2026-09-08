import { useState } from 'react'
import { Alert, Box, Button, Chip, Divider, Drawer, IconButton, Stack, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import GroupAddIcon from '@mui/icons-material/GroupAddOutlined'
import { useStore } from '../state/store'
import { readableRole } from '../state/selectors'
import { PersonaAvatar } from '../common/PersonaAvatar'
import { Row } from '../common/Row'

export function ParticipantsDrawer() {
  const { ui, data, dispatch, currentActor, actorById } = useStore()
  const [notice, setNotice] = useState<string | null>(null)

  const conv = ui.selectedConversationId ? data.conversations.get(ui.selectedConversationId) : null

  const close = () => dispatch({ type: 'toggle_participants', open: false })

  const isAdmin = currentActor.role === 'ff_admin'
  const isSeller = currentActor.role === 'seller'

  if (!conv) {
    return (
      <Drawer
        anchor="right"
        open={ui.showParticipants}
        onClose={close}
        slotProps={{ paper: { sx: { width: 360 } } }}
      >
        <Box sx={{ p: 3 }}>
          <Typography variant="subtitle1">Канал не выбран</Typography>
        </Box>
      </Drawer>
    )
  }

  const participants = conv.participantIds
    .map((id) => actorById.get(id))
    .filter((a): a is NonNullable<typeof a> => Boolean(a))

  return (
    <Drawer
      anchor="right"
      open={ui.showParticipants}
      onClose={close}
      slotProps={{ paper: { sx: { width: 380 } } }}
      data-testid="participants-drawer"
    >
      <Box sx={{ p: 2.5, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Row align="center" justify="space-between">
          <Stack>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Участники канала
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {conv.title}
            </Typography>
          </Stack>
          <IconButton onClick={close} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Row>
      </Box>
      <Box sx={{ p: 2 }}>
        <Row align="center" spacing={1}>
          <Chip size="small" label={`${participants.length} участников`} sx={{ fontWeight: 700 }} />
          {conv.pinned ? <Chip size="small" color="primary" label="Закреплён" /> : null}
          {conv.muted ? <Chip size="small" color="warning" label="Заглушён" /> : null}
          {conv.archived ? <Chip size="small" label="В архиве" sx={{ bgcolor: 'action.hover' }} /> : null}
        </Row>
      </Box>
      <Divider />
      <Stack sx={{ flex: 1, overflow: 'auto', p: 1 }} divider={<Divider flexItem />}>
        {participants.map((p) => (
          <Row key={p.id} align="center" spacing={1.25} sx={{ p: 1.25 }}>
            <PersonaAvatar actor={p} size={40} />
            <Stack sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                {p.name}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {readableRole(p.role)}
                {p.title ? ` · ${p.title}` : ''}
              </Typography>
            </Stack>
            <Chip
              size="small"
              label={p.role === 'seller' ? 'Селлер' : p.role === 'ff_admin' ? 'Админ' : 'Оператор'}
              sx={{
                bgcolor: p.role === 'seller' ? 'info.light' : p.role === 'ff_admin' ? 'primary.main' : 'action.hover',
                color: p.role === 'seller' ? 'info.main' : p.role === 'ff_admin' ? 'primary.contrastText' : 'text.primary',
                fontWeight: 700,
              }}
            />
          </Row>
        ))}
      </Stack>
      <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider' }}>
        {notice ? (
          <Alert severity="warning" sx={{ mb: 1 }} onClose={() => setNotice(null)}>
            {notice}
          </Alert>
        ) : null}
        <Button
          fullWidth
          variant="contained"
          startIcon={<GroupAddIcon />}
          disabled={!isAdmin}
          onClick={() => {
            if (!isAdmin) {
              setNotice(
                isSeller
                  ? 'Селлер не может менять состав канала. Обратитесь к админу ФФ.'
                  : 'Оператор ФФ не может приглашать. Только админ ФФ по правилу дизайна.',
              )
              return
            }
            setNotice('Демо: приглашение — заглушка. В бэкенде это создаст участника канала.')
          }}
        >
          {isAdmin ? 'Пригласить участника' : 'Приглашения — только у админа ФФ'}
        </Button>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Аудит-лог изменений состава (кто и когда добавил/удалил) — на бэкенде; в UI показываем ссылкой на историю канала.
        </Typography>
      </Box>
    </Drawer>
  )
}
