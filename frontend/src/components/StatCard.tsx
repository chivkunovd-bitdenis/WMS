import type { ReactNode } from 'react'
import { Card } from '../ui/Card'

type Props = {
  label: string
  value: ReactNode
  hint?: string
  tone?: 'neutral' | 'accent'
  'data-testid'?: string
}

export function StatCard({ label, value, hint, tone = 'neutral', ...rest }: Props) {
  return (
    <Card className={`card stat-card stat-card--${tone}`} {...rest}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </Card>
  )
}

