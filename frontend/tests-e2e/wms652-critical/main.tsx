import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import { muiTheme } from '../../src/mui/theme'
import { WmsDatePickersProvider } from '../../src/mui/WmsDatePickersProvider'
import { FfFbsOrdersScreen } from '../../src/screens/v2/FfFbsOrdersScreen'
import '../../src/index.css'
import '../../src/ui/ui.css'
// No UI/print module mocks: only CDP intercepts synthetic network responses.
const token = 'synthetic-wms666'
const authHeaders = () => ({ Authorization: `Bearer ${token}` })
createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={muiTheme}><WmsDatePickersProvider><BrowserRouter>
    <FfFbsOrdersScreen token={token} authHeaders={authHeaders} sellers={[]} />
  </BrowserRouter></WmsDatePickersProvider></ThemeProvider>,
)
