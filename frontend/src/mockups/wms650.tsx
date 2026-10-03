import { StrictMode, useCallback, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Box, Button, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../mui/theme'
import { Wms650Screen, type Wms650Api } from './wms650Screen'
import '../index.css'

// Отдельная точка входа макета WMS-650: /wms650-mockup.html
// Копии экрана нет: рендерится вариант настоящего экрана раскладки на настоящих
// компонентах и теме продукта. Сервера нет, состояние живёт в памяти.

// Коды те же, что в заглушке продукта (objectsStub.ts). Кнопки ленты «пикают» код
// так же, как поле сканера: можно и набрать его руками в поле экрана.
const DEMO_SCANS: Array<{ label: string; code: string }> = [
  { label: 'Ячейка А 1.2', code: '2000000000121' },
  { label: 'Ячейка Б 1.1', code: '2000000000411' },
  { label: 'Короб КР-000480', code: '2200000004807' },
  { label: 'Грузоместо ГМ-000318', code: '2300000003185' },
  { label: 'Палета П-000131', code: '2100000001311' },
  { label: 'Термокружка', code: '4601122334455' },
  { label: 'Футболка M', code: '4680123456789' },
  { label: 'Носки', code: '4600987654338' },
]

export function Wms650Harness() {
  const [note, setNote] = useState<string | null>(null)
  const [run, setRun] = useState(0)
  const [api, setApi] = useState<Wms650Api | null>(null)
  const onReady = useCallback((next: Wms650Api) => setApi(next), [])
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Box sx={{ px: 3, py: 1.5, bgcolor: 'text.primary', color: 'common.white' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            ЭТО НЕ ЭКРАН
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.75 }}>
            Лента макета WMS-650: данные выдуманные, сервера нет.
          </Typography>
          {note ? (
            <Typography variant="body2" sx={{ opacity: 0.85 }} data-testid="objects-note">
              {note}
            </Typography>
          ) : null}
        </Stack>
        <Stack direction="row" spacing={0.5} sx={{ mt: 0.75, alignItems: 'center', flexWrap: 'wrap', gap: 0.5 }}>
          <Typography variant="caption" sx={{ opacity: 0.75, mr: 1 }}>
            Пикнуть:
          </Typography>
          {DEMO_SCANS.map((one) => (
            <Button
              key={one.code}
              size="small"
              // Кнопка ленты не уводит фокус из поля сканера, как не уводит его сам сканер.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => api?.scan(one.code)}
              data-testid={`demo-scan-${one.code}`}
              sx={{ color: 'common.white', border: '1px solid rgba(255,255,255,0.35)', textTransform: 'none', py: 0, minHeight: 24 }}
            >
              {one.label}
            </Button>
          ))}
          <Button
            size="small"
            onClick={() => {
              setNote(null)
              setApi(null)
              setRun((current) => current + 1)
            }}
            data-testid="demo-reset"
            sx={{ color: 'common.white', textDecoration: 'underline', textTransform: 'none', py: 0, minHeight: 24, ml: 1 }}
          >
            Начать заново
          </Button>
        </Stack>
      </Box>
      <Box sx={{ display: 'flex' }}>
        <Box sx={{ width: 260, flexShrink: 0, bgcolor: 'background.paper' }} />
        <Box sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
          <Wms650Screen key={run} onNote={setNote} onReady={onReady} />
        </Box>
      </Box>
    </Box>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <Wms650Harness />
    </ThemeProvider>
  </StrictMode>,
)
