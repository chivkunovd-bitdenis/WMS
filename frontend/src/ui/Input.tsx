import type { InputHTMLAttributes } from 'react'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  uiSize?: 'md'
}

export function Input({ className, uiSize = 'md', ...props }: Props) {
  const cls = ['ui-input', `ui-input--${uiSize}`, className ?? '']
    .filter(Boolean)
    .join(' ')
  return <input {...props} className={cls} />
}

