import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { Card } from '../ui/Card'
import { PageHeader } from '../ui/PageHeader'

type ScreenProps = {
  title: string
  subtitle?: string
  children: ReactNode
}

export function Screen({ title, subtitle, children }: ScreenProps) {
  return (
    <Box>
      <PageHeader title={title} description={subtitle} />
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {children}
      </Box>
    </Box>
  )
}

export function PlaceholderCard({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children?: ReactNode
}) {
  return (
    <Card className="card">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 16 }}>{title}</h3>
          {hint ? <p className="subtle">{hint}</p> : null}
        </div>
        {children}
      </div>
    </Card>
  )
}

