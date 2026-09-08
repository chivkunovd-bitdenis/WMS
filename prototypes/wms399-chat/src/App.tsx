import { useEffect } from 'react'
import { Box, useMediaQuery } from '@mui/material'
import { useStore } from './state/store'
import { TopBar } from './shell/TopBar'
import { DemoStateDrawer } from './shell/DemoStateDrawer'
import { InboxScreen } from './inbox/InboxScreen'
import { ConversationScreen } from './conversation/ConversationScreen'
import { SearchScreen } from './search/SearchScreen'
import { NotificationsScreen } from './notifications/NotificationsScreen'
import { PreferencesScreen } from './notifications/PreferencesScreen'
import { Lightbox } from './conversation/Lightbox'
import { ParticipantsDrawer } from './participants/ParticipantsDrawer'
import { DocumentPickerDialog } from './conversation/DocumentPickerDialog'
import { DocumentPreviewDrawer } from './conversation/DocumentPreviewDrawer'
import { OfflineBanner } from './shell/OfflineBanner'

type RouteInfo = {
  screen: 'inbox' | 'conversation' | 'search' | 'notifications' | 'prefs'
  conversationId?: string
  threadRootId?: string
  flashMessageId?: string
}

function parseRoute(hash: string): RouteInfo {
  const cleaned = hash.replace(/^#/, '')
  const [pathPart, queryPart] = cleaned.split('?')
  const q = new URLSearchParams(queryPart ?? '')
  const path = (pathPart ?? '').replace(/^\//, '') || 'inbox'
  const segments = path.split('/')
  if (segments[0] === 'c' && segments[1]) {
    const conversationId = segments[1]
    let threadRootId: string | undefined
    if (segments[2] === 't' && segments[3]) threadRootId = segments[3]
    return { screen: 'conversation', conversationId, threadRootId, flashMessageId: q.get('msg') ?? undefined }
  }
  if (segments[0] === 'search') return { screen: 'search' }
  if (segments[0] === 'notifications') return { screen: 'notifications' }
  if (segments[0] === 'prefs') return { screen: 'prefs' }
  return { screen: 'inbox' }
}

export function App() {
  const { ui, dispatch, actions } = useStore()
  const isNarrow = useMediaQuery('(max-width: 720px)')

  useEffect(() => {
    dispatch({ type: 'set_viewport', viewport: isNarrow ? 'narrow' : 'desktop' })
  }, [isNarrow, dispatch])

  useEffect(() => {
    const onHash = () => dispatch({ type: 'set_route', route: window.location.hash || '#/inbox' })
    window.addEventListener('hashchange', onHash)
    window.addEventListener('popstate', onHash)
    if (!window.location.hash) window.location.hash = '#/inbox'
    return () => {
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener('popstate', onHash)
    }
  }, [dispatch])

  const route = parseRoute(ui.route)

  useEffect(() => {
    if (route.screen === 'conversation' && route.conversationId && route.conversationId !== ui.selectedConversationId) {
      actions.openConversation(route.conversationId, {
        threadRootId: route.threadRootId,
        flashMessageId: route.flashMessageId,
      })
    }
  }, [route.screen, route.conversationId, route.threadRootId, route.flashMessageId, ui.selectedConversationId, actions])

  const contentByScreen = () => {
    if (route.screen === 'search') return <SearchScreen />
    if (route.screen === 'notifications') return <NotificationsScreen />
    if (route.screen === 'prefs') return <PreferencesScreen />
    return null
  }

  const specialScreen = contentByScreen()

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
        bgcolor: 'background.default',
      }}
      data-testid="chat-app"
    >
      <TopBar />
      <OfflineBanner />
      <Box sx={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        {specialScreen ? (
          <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', p: { xs: 2, md: 3 } }}>{specialScreen}</Box>
        ) : ui.viewport === 'desktop' ? (
          <>
            <Box sx={{ width: 340, minHeight: 0, borderRight: '1px solid', borderColor: 'divider', overflow: 'hidden', display: 'flex', flexDirection: 'column', bgcolor: 'background.paper' }}>
              <InboxScreen />
            </Box>
            <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
              <ConversationScreen />
            </Box>
          </>
        ) : route.screen === 'conversation' ? (
          <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
            <ConversationScreen />
          </Box>
        ) : (
          <Box sx={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            <InboxScreen />
          </Box>
        )}
      </Box>
      <DemoStateDrawer />
      <Lightbox />
      <ParticipantsDrawer />
      <DocumentPickerDialog />
      <DocumentPreviewDrawer />
    </Box>
  )
}
