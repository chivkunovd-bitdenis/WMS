import type { SelectHTMLAttributes } from 'react'

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  uiSize?: 'md'
}

export function Select({ className, uiSize = 'md', ...props }: Props) {
  const cls = ['ui-select', `ui-select--${uiSize}`, className ?? '']
    .filter(Boolean)
    .join(' ')
  return <select {...props} className={cls} />
}

