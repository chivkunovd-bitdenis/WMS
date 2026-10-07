import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import { muiTheme } from '../../src/mui/theme'
import { WmsDatePickersProvider } from '../../src/mui/WmsDatePickersProvider'
import { FfFbsOrdersScreen } from '../../src/screens/v2/FfFbsOrdersScreen'
import '../../src/index.css'
import '../../src/ui/ui.css'

// The audit API proxy replaces this synthetic auth value with its own isolated
// test actor. No credential is stored in the evidence artifact.
const token = 'native-print-proof-test-actor'
const authHeaders = () => ({ Authorization: `Bearer ${token}` })

createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={muiTheme}>
    <WmsDatePickersProvider>
      <BrowserRouter>
        <FfFbsOrdersScreen token={token} authHeaders={authHeaders} sellers={[]} />
      </BrowserRouter>
    </WmsDatePickersProvider>
  </ThemeProvider>,
)
