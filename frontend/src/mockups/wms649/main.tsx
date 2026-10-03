import { StrictMode, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'

import '../../index.css'
import '../../ui/ui.css'
import { installStubFetch } from '../../screens/ff/knowledge/scenes/stubFetch'
import { installAssetFetch } from './assets'
import { installPrintGuard } from './printGuard'
import { buildRoutes } from './routes'
import { FORMS } from './forms'
import { Chrome } from './Chrome'
import { runtime } from './runtime'
import { WmsDatePickersProvider } from '../../mui/WmsDatePickersProvider'
import { muiTheme } from '../../mui/theme'
import { CssBaseline, ThemeProvider } from '@mui/material'
import type { MockMode } from './forms'
import type { Marketplace } from './products'

// Точка входа макета WMS-649. Подставной сервер и защита от настоящей печати
// ставятся один раз и не снимаются: страница живёт только как макет.
installPrintGuard()
installStubFetch(buildRoutes([...new Set(FORMS.flatMap((form) => form.routes))]))
installAssetFetch()

function readInitial(): { form: string; mode: MockMode; doc: Marketplace } {
  const params = new URLSearchParams(window.location.search)
  const form = FORMS.some((item) => item.id === params.get('form')) ? params.get('form')! : FORMS[0]!.id
  const mode: MockMode = params.get('mode') === 'now' ? 'now' : 'proposal'
  const doc: Marketplace = params.get('doc') === 'ozon' ? 'ozon' : 'wb'
  return { form, mode, doc }
}

// eslint-disable-next-line react-refresh/only-export-components -- точка входа: экспортов нет
function App() {
  const initial = useMemo(() => readInitial(), [])
  const [formId, setFormId] = useState(initial.form)
  const [mode, setMode] = useState<MockMode>(initial.mode)
  const [doc, setDoc] = useState<Marketplace>(initial.doc)
  const form = FORMS.find((item) => item.id === formId) ?? FORMS[0]!
  // Подставной сервер читает режим в момент запроса. Layout-эффект срабатывает
  // раньше обычных эффектов экранов, из которых уходят первые запросы.
  useLayoutEffect(() => {
    runtime.mode = mode
    runtime.doc = doc
  }, [mode, doc])

  useEffect(() => {
    const params = new URLSearchParams({ form: formId, mode, doc })
    window.history.replaceState(null, '', `?${params.toString()}`)
  }, [formId, mode, doc])

  // Тема продукта — на весь макет: окна и переключатели, которые макет рисует сам
  // или открывает вне оболочки портала, должны выглядеть так же, как в продукте.
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <WmsDatePickersProvider>
        <Chrome
          forms={FORMS}
          form={form}
          onForm={setFormId}
          mode={mode}
          onMode={setMode}
          doc={doc}
          onDoc={setDoc}
        />
        {/* key: смена формы, режима или документа пересобирает экран с нуля —
            так оверлей и настоящие окна не тащат состояние из прошлой формы. */}
        <div key={`${form.id}|${mode}|${form.docToggle ? doc : '-'}`}>
          {form.render({ mode, doc })}
        </div>
      </WmsDatePickersProvider>
    </ThemeProvider>
  )
}

// Корень переиспользуем: при горячей перезагрузке модуля второй createRoot на том же
// контейнере React не допускает.
type RootHost = HTMLElement & { __wms649Root?: ReturnType<typeof createRoot> }
const container = document.getElementById('root') as RootHost
const root = container.__wms649Root ?? createRoot(container)
container.__wms649Root = root
root.render(
  <StrictMode>
    <App />
  </StrictMode>,
)
