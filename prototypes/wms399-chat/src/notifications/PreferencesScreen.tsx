import { Alert, Box, Button, Divider, FormControlLabel, MenuItem, Paper, Radio, RadioGroup, Stack, Switch, TextField, Typography } from '@mui/material'
import { useStore } from '../state/store'
import { Row } from '../common/Row'
import { conversationAccessible } from '../state/selectors'
import type { NotificationPrefs } from '../types'

export function PreferencesScreen() {
  const { ui, dispatch, data, dispatchData, currentActor } = useStore()
  const prefs = ui.notificationPrefs

  const set = (patch: Partial<NotificationPrefs>) => dispatch({ type: 'set_prefs', patch })

  const conversations = Array.from(data.conversations.values()).filter((c) =>
    conversationAccessible(c, currentActor),
  )

  const requestPush = () => {
    if (!('Notification' in window)) {
      set({ pushPermission: 'denied', pushEnabled: false })
      return
    }
    Notification.requestPermission()
      .then((res) => set({ pushPermission: res as NotificationPrefs['pushPermission'], pushEnabled: res === 'granted' }))
      .catch(() => set({ pushPermission: 'denied', pushEnabled: false }))
  }

  const pushBanner = (() => {
    if (prefs.pushEnabled && prefs.pushPermission !== 'granted') {
      return (
        <Alert severity="warning">
          Браузер не разрешил уведомления. Нажмите «Запросить разрешение» — если запретите, push не пойдут, и это будет видно здесь.
        </Alert>
      )
    }
    if (prefs.pushPermission === 'denied') {
      return (
        <Alert severity="error">
          Разрешение на push запрещено в браузере. Разрешить можно в настройках сайта.
        </Alert>
      )
    }
    return null
  })()

  return (
    <Stack sx={{ maxWidth: 780, mx: 'auto', gap: 2 }} data-testid="prefs-screen">
      <Box>
        <Typography variant="h5" sx={{ fontWeight: 800 }}>
          Настройки уведомлений
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Прототип не отправляет реальные push и email — это макет проектируемых параметров.
        </Typography>
      </Box>
      {pushBanner}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Push в браузере
        </Typography>
        <Row align="center" spacing={2} wrap sx={{ rowGap: 1 }}>
          <FormControlLabel
            control={
              <Switch
                checked={prefs.pushEnabled}
                onChange={(e) => set({ pushEnabled: e.target.checked })}
              />
            }
            label="Присылать push"
          />
          <Button size="small" variant="outlined" onClick={requestPush}>
            Запросить разрешение (реальный браузер)
          </Button>
          <Typography variant="caption" color="text.secondary">
            Статус: {prefs.pushPermission === 'granted' ? 'разрешены' : prefs.pushPermission === 'denied' ? 'запрещены' : 'не запрошены'}
          </Typography>
        </Row>
        <Box sx={{ mt: 1.5, p: 1.5, borderRadius: 2, bgcolor: 'action.hover' }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Демо-состояние разрешения (без реального запроса)
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            Только для просмотра баннеров прототипа. Меняет отображаемый статус
            локально и не трогает системное разрешение браузера.
          </Typography>
          <RadioGroup
            row
            value={prefs.pushPermission}
            onChange={(e) => set({ pushPermission: e.target.value as NotificationPrefs['pushPermission'] })}
          >
            <FormControlLabel value="default" control={<Radio size="small" />} label="не запрошены" />
            <FormControlLabel value="granted" control={<Radio size="small" />} label="разрешены" />
            <FormControlLabel value="denied" control={<Radio size="small" />} label="запрещены" />
          </RadioGroup>
        </Box>
        <FormControlLabel
          sx={{ mt: 1, display: 'block' }}
          control={
            <Switch
              checked={prefs.mentionsOnly}
              onChange={(e) => set({ mentionsOnly: e.target.checked })}
            />
          }
          label="Только на упоминания"
        />
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Digest email
        </Typography>
        <RadioGroup
          value={prefs.digest}
          onChange={(e) => set({ digest: e.target.value as NotificationPrefs['digest'] })}
        >
          <FormControlLabel value="off" control={<Radio size="small" />} label="Не присылать" />
          <FormControlLabel value="hourly" control={<Radio size="small" />} label="Раз в час, если есть непрочитанное" />
          <FormControlLabel value="daily" control={<Radio size="small" />} label="Раз в день, утро" />
        </RadioGroup>
        <Typography variant="caption" color="text.secondary">
          В MVP digest не гарантирован — уточним с владельцем; прототип оставляет здесь заготовку контракта.
        </Typography>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          По каналам
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Заглушение канала — не влияет на упоминания. Упоминания приходят всегда.
        </Typography>
        <Divider sx={{ my: 1 }} />
        <Stack divider={<Divider flexItem />}>
          {conversations.map((c) => {
            const muted = prefs.perConversation[c.id]?.muted ?? c.muted
            return (
              <Row key={c.id} align="center" spacing={1.25} sx={{ py: 1 }}>
                <Stack sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                    {c.title}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" noWrap>
                    {c.subtitle}
                  </Typography>
                </Stack>
                <TextField
                  select
                  size="small"
                  value={muted ? 'muted' : 'active'}
                  onChange={(e) => {
                    const next = e.target.value === 'muted'
                    set({
                      perConversation: {
                        ...prefs.perConversation,
                        [c.id]: { muted: next },
                      },
                    })
                    dispatchData({ type: 'mute', conversationId: c.id, muted: next })
                  }}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="active">Уведомлять</MenuItem>
                  <MenuItem value="muted">Заглушить</MenuItem>
                </TextField>
              </Row>
            )
          })}
        </Stack>
      </Paper>
    </Stack>
  )
}
