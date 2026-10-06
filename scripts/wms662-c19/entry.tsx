import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider, CssBaseline, Button } from '@mui/material'
import { BrowserRouter } from 'react-router-dom'
import { muiTheme } from '/src/mui/theme'
import { FfFbsSupplyWorkspace } from '/src/screens/v2/FfFbsSupplyWorkspace'
const ah = (token: string) => ({Authorization: `Bearer ${token}`})
const supplyId = new URLSearchParams(location.search).get('supply')!
function App() {
 const [open, setOpen] = useState(true)
 return <ThemeProvider theme={muiTheme}><CssBaseline/><BrowserRouter>
  <Button data-testid="fixture-reopen" onClick={() => setOpen(true)}>Открыть поставку</Button>
  <FfFbsSupplyWorkspace token="fixture-only" authHeaders={ah} supplyId={supplyId}
   open={open} onClose={() => setOpen(false)} />
 </BrowserRouter></ThemeProvider>
}
createRoot(document.getElementById('root')!).render(<App/> )
