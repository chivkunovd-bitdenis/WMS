import { useEffect, useState } from 'react'
import { Box, GlobalStyles } from '@mui/material'
import { apiUrl } from '../api'

const bannerHeight = 48

export function StagingBanner() {
  const [staging, setStaging] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void fetch(apiUrl('/health'), {
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) return
        const health: unknown = await response.json()
        if (typeof health === 'object' && health !== null && 'app_env' in health) {
          setStaging(health.app_env === 'staging')
        }
      })
      .catch(() => {
        // The runtime environment is the only source for the staging indicator.
      })
    return () => controller.abort()
  }, [])

  if (!staging) return null

  return (
    <>
      <GlobalStyles styles={{
        // Fixed shell elements and body-mounted dialogs also need the reserved band.
        '#root [data-testid="app-topbar"]': { top: bannerHeight },
        'html body .MuiDrawer-paper': {
          top: bannerHeight,
          height: `calc(100% - ${bannerHeight}px)`,
        },
        'html body .MuiModal-root': { top: bannerHeight },
        '#root [data-testid="app-frame"], #root .app-frame': {
          minHeight: `calc(100svh - ${bannerHeight}px)`,
        },
        '#root .app-sidebar, #root .app-topbar': { top: bannerHeight },
      }} />
      <Box
        role="status"
        data-testid="staging-banner"
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: (theme) => theme.zIndex.tooltip + 1,
          width: '100%',
          height: bannerHeight,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxSizing: 'border-box',
          px: 2,
          backgroundColor: '#ffdf00',
          color: '#1c1800',
          borderBottom: '2px solid #a88d00',
          fontSize: { xs: 18, sm: 20 },
          fontWeight: 900,
          letterSpacing: '0.04em',
          lineHeight: 1.2,
        }}
      >
        ТЕСТОВЫЙ КОНТУР
      </Box>
    </>
  )
}
