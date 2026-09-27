import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppBar, Box, Button, CssBaseline, GlobalStyles, Paper, ThemeProvider, Toolbar, Typography } from '@mui/material'
import { MemoryRouter } from 'react-router-dom'

import { WmsBrandMark } from '../../components/WmsBrandMark'
import { muiTheme } from '../../mui/theme'
import { SellerKizWithdrawalAcceptanceScreen } from './SellerKizWithdrawalAcceptanceScreen'
import '../../index.css'

export function LocalDemoShell() {
  return (
    <Box sx={{ minHeight: '100vh', maxWidth: '100vw', overflowX: 'hidden', bgcolor: 'background.default' }}>
      <AppBar position="sticky" color="inherit" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 1.5, minWidth: 0 }}>
          <WmsBrandMark size={40} portal="seller" />
          <Typography variant="h6" noWrap sx={{ fontWeight: 900, flexShrink: 0 }}>Короб ВМС</Typography>
          <Typography variant="body2" color="text.secondary" noWrap sx={{ display: { xs: 'none', sm: 'block' }, minWidth: 0 }}>Портал селлера · Империя львов</Typography>
          <Button size="small" variant="outlined" disabled sx={{ ml: 'auto', flexShrink: 0 }}>Демо</Button>
        </Toolbar>
      </AppBar>

      <Box sx={{ display: 'flex', width: '100%', minWidth: 0 }}>
        <Paper
          component="aside"
          square
          elevation={0}
          sx={{
            display: { xs: 'none', md: 'block' }, width: 220, flex: '0 0 220px', minHeight: 'calc(100vh - 64px)',
            borderRight: '1px solid', borderColor: 'divider', borderRadius: 0, p: 1.5,
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ px: 1 }}>РАЗДЕЛЫ</Typography>
          <Paper variant="outlined" sx={{ mt: 1, px: 1.5, py: 1, bgcolor: 'rgba(91,33,182,.08)', color: 'primary.main', fontWeight: 700 }}>Честный знак</Paper>
        </Paper>

        <Box component="main" sx={{ minWidth: 0, width: { xs: '100%', md: 'calc(100% - 220px)' }, p: { xs: 1.25, sm: 2, md: 3 }, overflowX: 'hidden' }}>
          <SellerKizWithdrawalAcceptanceScreen />
        </Box>
      </Box>
    </Box>
  )
}

const container = document.getElementById('root')
if (container) {
  createRoot(container).render(
    <StrictMode>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        <GlobalStyles styles={{ 'html, body, #root': { maxWidth: '100%', overflowX: 'hidden' } }} />
        <MemoryRouter>
          <LocalDemoShell />
        </MemoryRouter>
      </ThemeProvider>
    </StrictMode>,
  )
}
