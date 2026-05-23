import { forwardRef } from 'react'
import type { SelectHTMLAttributes } from 'react'

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  uiSize?: 'md'
}

export const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { className, uiSize = 'md', ...props },
  ref,
) {
  const cls = ['ui-select', `ui-select--${uiSize}`, className ?? '']
    .filter(Boolean)
    .join(' ')
  return <select ref={ref} {...props} className={cls} />
})

