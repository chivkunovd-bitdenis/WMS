import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react'
import { Alert, Box, Button, Container, Typography } from '@mui/material'
import { useLocation, useRouteError } from 'react-router-dom'
import { WmsBrandMark, type WmsPortal } from '../WmsBrandMark'
import { nextRecovery } from '../../utils/errorRecovery'
import { reloadChunkOnce, reportClientError } from '../../utils/clientErrorReport'

type Props = {
  children: ReactNode
  screen?: string
  component: string
  root?: boolean
  resetKey?: string
  portal?: WmsPortal
}
type State = { failed: boolean; fallback: boolean; generation: number }

function ErrorFallback({ root, portal }: Pick<Props, 'root' | 'portal'>) {
  const notice = (
    <Alert severity="error" data-testid="client-error-fallback" action={
      <Button color="inherit" onClick={() => window.location.reload()}>Обновить</Button>
    }>
      Не удалось показать этот раздел. Обновите страницу.
    </Alert>
  )
  if (!root) return notice
  return (
    <Box component="main" sx={{ minHeight: '100vh', bgcolor: 'background.default', py: { xs: 3, sm: 5 }, px: 2 }}>
      <Container maxWidth="sm">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
          <WmsBrandMark size={48} portal={portal} />
          <Typography variant="h5" component="h1" sx={{ fontWeight: 900 }}>Короб ВМС</Typography>
        </Box>
        {notice}
      </Container>
    </Box>
  )
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, fallback: false, generation: 0 }
  private failures: number[] = []
  private timer: ReturnType<typeof setTimeout> | undefined

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    reportClientError(error, {
      screen: this.props.screen,
      component: this.props.component,
      action: `react${info.componentStack ?? ''}`,
    })
    if (reloadChunkOnce(error)) return
    const decision = nextRecovery(this.failures, Date.now())
    this.failures = decision.failures
    if (decision.fallback) {
      this.setState({ fallback: true })
    } else if (decision.delayMs) {
      this.timer = setTimeout(this.retry, decision.delayMs)
    } else {
      this.retry()
    }
  }

  componentDidUpdate(previous: Props) {
    if (previous.resetKey !== this.props.resetKey) {
      clearTimeout(this.timer)
      this.failures = []
      // Keep healthy shells and dialogs mounted during normal navigation.
      if (this.state.failed) this.retry()
    }
  }

  componentWillUnmount() {
    clearTimeout(this.timer)
  }

  private retry = () => {
    this.setState(({ generation }) => ({ failed: false, fallback: false, generation: generation + 1 }))
  }

  render() {
    if (this.state.fallback) return <ErrorFallback root={this.props.root} portal={this.props.portal} />
    if (this.state.failed) return null
    return <Fragment key={this.state.generation}>{this.props.children}</Fragment>
  }
}

/** A new route starts with its own recovery window, even for parameterised paths. */
export function SectionErrorBoundary(props: Props) {
  const { pathname } = useLocation()
  return <ErrorBoundary {...props} resetKey={pathname} screen={pathname} />
}

function RethrowRouteError({ error }: { error: unknown }): never {
  throw error
}

/** Explicit data-router last resort; never use react-router's technical error page. */
export function RootRouteError({ portal }: { portal: WmsPortal }) {
  const error = useRouteError()
  return (
    <SectionErrorBoundary component="router" root portal={portal}>
      <RethrowRouteError error={error} />
    </SectionErrorBoundary>
  )
}
