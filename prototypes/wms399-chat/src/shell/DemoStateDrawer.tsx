import {
  Box,
  Button,
  Divider,
  Drawer,
  FormControlLabel,
  IconButton,
  Radio,
  RadioGroup,
  Stack,
  Switch,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import { useStore } from '../state/store'
import { PersonaAvatar } from '../common/PersonaAvatar'
import { readableRole } from '../state/selectors'
import type { Role } from '../types'

const ROLE_LABEL: Record<Role, string> = {
  ff_admin: 'Админ ФФ (видит всех)',
  ff_operator: 'Оператор ФФ (Хамовники)',
  seller: 'Селлер (Ловиана)',
}

export function DemoStateDrawer() {
  const { ui, currentActor, actorById, dispatch } = useStore()

  const close = () => dispatch({ type: 'toggle_demo_menu', open: false })

  const setDemo = (patch: Partial<typeof ui.demo>) => dispatch({ type: 'set_demo', patch })

  const rolePeople = Array.from(actorById.values())

  return (
    <Drawer
      anchor="right"
      open={ui.showDemoMenu}
      onClose={close}
      PaperProps={{ sx: { width: 360, p: 0 } }}
    >
      <Box sx={{ px: 3, py: 2.5, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Демо-состояния
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Переключаем роль, ширину и принудительные сбои. Это только макет.
            </Typography>
          </Stack>
          <IconButton onClick={close} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Stack>
      </Box>
      <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Stack spacing={1.25}>
          <Typography variant="subtitle2">Роль просмотра</Typography>
          <RadioGroup
            value={ui.role}
            onChange={(e) => dispatch({ type: 'set_role', role: e.target.value as Role })}
          >
            {(['ff_admin', 'ff_operator', 'seller'] as Role[]).map((r) => (
              <FormControlLabel key={r} value={r} control={<Radio size="small" />} label={ROLE_LABEL[r]} />
            ))}
          </RadioGroup>
          <Typography variant="caption" color="text.secondary">
            Селлер не видит внутренние заметки склада; переключите роль, чтобы это сравнить.
          </Typography>
        </Stack>
        <Divider />
        <Stack spacing={1.25}>
          <Typography variant="subtitle2">Активный пользователь</Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ p: 1.25, bgcolor: 'action.hover', borderRadius: 2 }}>
            <PersonaAvatar actor={currentActor} size={40} />
            <Stack sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
                {currentActor.name}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {readableRole(currentActor.role)} · {currentActor.title ?? ''}
              </Typography>
            </Stack>
          </Stack>
          <RadioGroup
            value={currentActor.id}
            onChange={(e) => dispatch({ type: 'set_actor', actorId: e.target.value })}
          >
            {rolePeople
              .filter((a) => a.role === ui.role)
              .map((a) => (
                <FormControlLabel
                  key={a.id}
                  value={a.id}
                  control={<Radio size="small" />}
                  label={`${a.name} · ${a.title ?? ''}`}
                />
              ))}
          </RadioGroup>
        </Stack>
        <Divider />
        <Stack spacing={1}>
          <Typography variant="subtitle2">Ширина экрана</Typography>
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            value={ui.viewport}
            onChange={(_, v) => v && dispatch({ type: 'set_viewport', viewport: v })}
          >
            <ToggleButton value="desktop">Десктоп (склад)</ToggleButton>
            <ToggleButton value="narrow">Мобильный (селлер)</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        <Divider />
        <Stack spacing={1}>
          <Typography variant="subtitle2">Принудительные сбои и состояния</Typography>
          <FormControlLabel
            control={<Switch checked={ui.demo.offline} onChange={(e) => setDemo({ offline: e.target.checked })} />}
            label="Оффлайн — сеть недоступна"
          />
          <FormControlLabel
            control={<Switch checked={ui.demo.forceUploadFail} onChange={(e) => setDemo({ forceUploadFail: e.target.checked })} />}
            label="Загрузка вложений падает"
          />
          <FormControlLabel
            control={<Switch checked={ui.demo.slowNetwork} onChange={(e) => setDemo({ slowNetwork: e.target.checked })} />}
            label="Медленная сеть (загрузка вдвое дольше)"
          />
          <FormControlLabel
            control={<Switch checked={ui.demo.documentOutdated} onChange={(e) => setDemo({ documentOutdated: e.target.checked })} />}
            label="Документы в карточках устарели"
          />
          <FormControlLabel
            control={<Switch checked={ui.demo.permissionDenied} onChange={(e) => setDemo({ permissionDenied: e.target.checked })} />}
            label="У пользователя закрыт доступ (403)"
          />
        </Stack>
        <Divider />
        <Button onClick={close} variant="contained" size="large">
          Готово
        </Button>
      </Box>
    </Drawer>
  )
}
