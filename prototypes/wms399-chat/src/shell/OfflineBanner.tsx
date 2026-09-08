import { Alert, Slide } from '@mui/material'
import { useStore } from '../state/store'

export function OfflineBanner() {
  const { ui } = useStore()
  const show = ui.demo.offline
  return (
    <Slide direction="down" in={show} mountOnEnter unmountOnExit>
      <Alert
        severity="warning"
        variant="filled"
        sx={{ borderRadius: 0, justifyContent: 'center' }}
      >
        Нет сети (демо). Сообщения не уходят, вложения падают с причиной «нет сети».
      </Alert>
    </Slide>
  )
}
