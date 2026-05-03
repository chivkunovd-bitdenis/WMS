import type { HTMLAttributes, ReactNode } from 'react'

type Props = HTMLAttributes<HTMLElement> & {
  as?: 'section' | 'div' | 'article'
  children: ReactNode
}

export function Card({ as = 'section', className, children, ...props }: Props) {
  const Tag = as
  const cls = ['ui-card', className ?? ''].filter(Boolean).join(' ')
  return (
    <Tag {...props} className={cls}>
      {children}
    </Tag>
  )
}

