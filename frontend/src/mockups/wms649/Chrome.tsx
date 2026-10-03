import { useEffect, useState } from 'react'
import {
  Alert,
  Badge,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { CssBaseline, ThemeProvider } from '@mui/material'

import { muiTheme } from '../../mui/theme'
import type { FormDef, MockMode } from './forms'
import type { Marketplace } from './products'
import { clearPrintJobs, setCurrentFormLabel, usePrintJobs, type PrintJob } from './printGuard'

/**
 * Рамка макета WMS-649: переключатель формы, режим «Сейчас / Предложение»,
 * документ WB или Ozon и журнал «что ушло бы на принтер». Рамка сидит над
 * настоящим порталом и сдвигает его фиксированную шапку и меню вниз, ничего
 * не меняя внутри.
 */

export const CHROME_HEIGHT = 92

function PrintLogDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const jobs = usePrintJobs()
  const [preview, setPreview] = useState<PrintJob | null>(null)
  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>Журнал печати макета</DialogTitle>
        <DialogContent>
          {jobs.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Пока ничего не печатали. В макете принтер не подключён: «Печать» кладёт задание сюда.
            </Typography>
          ) : (
            <Stack spacing={1.5}>
              {jobs.map((job) => (
                <Box
                  key={job.id}
                  sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5 }}
                  data-testid="wms649-print-job"
                >
                  <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="subtitle2">
                      {new Date(job.at).toLocaleTimeString('ru-RU')} · {job.title}
                    </Typography>
                    <Button size="small" onClick={() => setPreview(job)}>
                      Показать лист
                    </Button>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    {job.formLabel}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 0.5 }} data-testid="wms649-print-job-codes">
                    {job.barcodes.length > 0
                      ? job.barcodes.map((item) => `${item.code} × ${item.count}`).join(' · ')
                      : job.rows.length > 0
                        ? job.rows.join(' | ')
                        : 'Штрихкоды товара в задании не найдены'}
                  </Typography>
                </Box>
              ))}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={clearPrintJobs} disabled={jobs.length === 0}>
            Очистить
          </Button>
          <Button onClick={onClose}>Закрыть</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={preview !== null} onClose={() => setPreview(null)} maxWidth="md" fullWidth>
        <DialogTitle>{preview?.title}</DialogTitle>
        <DialogContent>
          {preview ? (
            <Box
              component="iframe"
              title="Предпросмотр печатной формы"
              sandbox=""
              srcDoc={preview.html}
              sx={{ width: '100%', height: 480, border: 1, borderColor: 'divider', bgcolor: '#fff' }}
            />
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreview(null)}>Закрыть</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

/**
 * Эмулятор сканера штрихкодов. Настоящий сканер «печатает» код нажатиями клавиш
 * с паузой в несколько миллисекунд и Enter в конце; страница продукта так и
 * распознаёт скан. Здесь те же нажатия шлёт макет — за человека, у которого нет
 * сканера под рукой.
 */
function emulateScan(code: string): void {
  const fire = (key: string) =>
    document.dispatchEvent(new KeyboardEvent('keydown', { key, code: key.length === 1 ? `Key${key.toUpperCase()}` : key, bubbles: true, cancelable: true }))
  for (const char of code) fire(char)
  fire('Enter')
}

function ScannerEmulator({ codes }: { codes: Array<{ label: string; code: string }> }) {
  return (
    <TextField
      select
      size="small"
      label="Эмулятор сканера"
      value=""
      onChange={(event) => {
        const code = event.target.value
        if (!code) return
        window.setTimeout(() => emulateScan(code), 0)
      }}
      sx={{ flex: '0 1 240px', minWidth: 180 }}
      data-testid="wms649-scanner"
    >
      {codes.map((item) => (
        <MenuItem key={item.code} value={item.code}>
          {item.label}
        </MenuItem>
      ))}
    </TextField>
  )
}

type Props = {
  forms: FormDef[]
  form: FormDef
  onForm: (id: string) => void
  mode: MockMode
  onMode: (mode: MockMode) => void
  doc: Marketplace
  onDoc: (doc: Marketplace) => void
}

export function Chrome({ forms, form, onForm, mode, onMode, doc, onDoc }: Props) {
  const jobs = usePrintJobs()
  const [logOpen, setLogOpen] = useState(false)
  const [toast, setToast] = useState<PrintJob | null>(null)
  const [lastSeen, setLastSeen] = useState(0)

  useEffect(() => {
    setCurrentFormLabel(`${form.title}${form.docToggle ? ` · документ ${doc === 'wb' ? 'WB' : 'Ozon'}` : ''}`)
  }, [form, doc])

  // Новое задание печати — показываем плашку. Подстраиваем состояние прямо при
  // рендере, а не эффектом: так нет лишнего прохода отрисовки.
  const latest = jobs[0]
  if (latest && latest.id > lastSeen) {
    setLastSeen(latest.id)
    setToast(latest)
  }

  const platformText =
    form.platformKnown === 'да'
      ? 'Площадка из документа: да'
      : form.platformKnown === 'нет'
        ? 'Площадка из документа: нет'
        : `Площадка из документа: да — ${doc === 'wb' ? 'WB' : 'Ozon'}`

  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <style>{`
        body { padding-top: ${CHROME_HEIGHT}px; }
        .MuiAppBar-positionFixed { top: ${CHROME_HEIGHT}px !important; }
        .MuiDrawer-docked .MuiDrawer-paper, .MuiDrawer-root.MuiDrawer-docked > .MuiPaper-root {
          top: ${CHROME_HEIGHT}px !important;
          height: calc(100% - ${CHROME_HEIGHT}px) !important;
        }
        /* Окна продукта открываются под рамкой, а не под ней и поверх неё: иначе
           рамка недоступна, пока открыто окно (поставка FBS открыта всегда). */
        .MuiDialog-container { padding-top: ${CHROME_HEIGHT}px !important; box-sizing: border-box; }
      `}</style>
      <Box
        data-testid="wms649-chrome"
        sx={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          height: CHROME_HEIGHT,
          zIndex: (theme) => theme.zIndex.modal + 5,
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
          px: 2,
          py: 1,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 0.75,
        }}
      >
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ alignItems: 'center', flexWrap: 'nowrap', minWidth: 0, overflowX: 'auto', py: 0.5 }}
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 800, whiteSpace: 'nowrap' }}>
            WMS-649 · макет
          </Typography>
          <TextField
            select
            size="small"
            label="Форма печати"
            value={form.id}
            onChange={(event) => onForm(event.target.value)}
            sx={{ flex: '1 1 260px', minWidth: 240, maxWidth: 480 }}
            data-testid="wms649-form-select"
          >
            {forms.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.title}
              </MenuItem>
            ))}
          </TextField>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={mode}
            onChange={(_event, next: MockMode | null) => {
              if (next) onMode(next)
            }}
            sx={{ flexShrink: 0, '& .MuiToggleButton-root': { whiteSpace: 'nowrap' } }}
            data-testid="wms649-mode"
          >
            <ToggleButton value="now" data-testid="wms649-mode-now">
              Сейчас
            </ToggleButton>
            <ToggleButton value="proposal" data-testid="wms649-mode-proposal">
              Предложение
            </ToggleButton>
          </ToggleButtonGroup>
          {form.scanCodes ? <ScannerEmulator codes={form.scanCodes(doc)} /> : null}
          {form.docToggle ? (
            <ToggleButtonGroup
              exclusive
              size="small"
              value={doc}
              onChange={(_event, next: Marketplace | null) => {
                if (next) onDoc(next)
              }}
              sx={{ flexShrink: 0, '& .MuiToggleButton-root': { whiteSpace: 'nowrap' } }}
              data-testid="wms649-doc"
            >
              <ToggleButton value="wb" data-testid="wms649-doc-wb">
                Док. WB
              </ToggleButton>
              <ToggleButton value="ozon" data-testid="wms649-doc-ozon">
                Док. Ozon
              </ToggleButton>
            </ToggleButtonGroup>
          ) : null}
          <Box sx={{ flexGrow: 1 }} />
          <Badge badgeContent={jobs.length} color="primary" invisible={jobs.length === 0} sx={{ flexShrink: 0 }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<PrintOutlined />}
              onClick={() => setLogOpen(true)}
              data-testid="wms649-log-open"
            >
              Журнал печати
            </Button>
          </Badge>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
          <Chip
            size="small"
            variant="outlined"
            color={form.platformKnown === 'нет' ? 'warning' : 'success'}
            label={platformText}
            data-testid="wms649-platform-known"
          />
          <Typography variant="caption" color="text.secondary" noWrap title={form.where}>
            {form.where}
          </Typography>
          <Typography variant="caption" sx={{ fontWeight: 600 }} noWrap title={form.hint}>
            · {form.hint}
          </Typography>
        </Stack>
      </Box>
      <PrintLogDialog open={logOpen} onClose={() => setLogOpen(false)} />
      <Snackbar
        open={toast !== null}
        autoHideDuration={7000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Alert
          severity="success"
          onClose={() => setToast(null)}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => {
                setToast(null)
                setLogOpen(true)
              }}
            >
              Журнал
            </Button>
          }
          data-testid="wms649-print-toast"
        >
          В макете принтера нет. Ушло бы на ленту:{' '}
          {toast?.barcodes.length
            ? toast.barcodes.map((item) => `${item.code} × ${item.count}`).join(' · ')
            : toast?.title}
        </Alert>
      </Snackbar>
    </ThemeProvider>
  )
}
