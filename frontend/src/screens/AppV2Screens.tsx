import type { ReactNode } from 'react'
import { Card } from '../ui/Card'

type ScreenProps = {
  title: string
  subtitle?: string
  children: ReactNode
}

export function Screen({ title, subtitle, children }: ScreenProps) {
  return (
    <div className="screen">
      <div className="screen-head">
        <div>
          <h2 className="screen-title">{title}</h2>
          {subtitle ? <p className="screen-subtitle">{subtitle}</p> : null}
        </div>
      </div>
      <div className="screen-body">{children}</div>
    </div>
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

