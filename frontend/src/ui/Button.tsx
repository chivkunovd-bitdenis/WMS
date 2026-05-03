import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  children: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  children,
  ...props
}: Props) {
  const cls = [
    'ui-button',
    `ui-button--${variant}`,
    `ui-button--${size}`,
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button {...props} className={cls}>
      {children}
    </button>
  )
}

