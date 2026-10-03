import type { MouseEvent, ReactNode } from 'react'

/**
 * WMS-649 · перехват нажатия на настоящую кнопку продукта.
 *
 * Нужен только там, где предложение меняет то, ЧТО кнопка печатает (лист
 * приёмки, лист упаковки, окно Честного знака без списка кодов). Кнопка на экране
 * настоящая, нажимает её человек; макет подменяет лишь данные, которые уйдут
 * в настоящую печатную функцию продукта.
 */

export type InterceptRule = {
  /** CSS-селектор настоящей кнопки. */
  selector: string
  /** Обработчик; получает найденную кнопку (или её обёртку). */
  handle: (element: HTMLElement) => void
}

function findHit(target: HTMLElement, selector: string): HTMLElement | null {
  const direct = target.closest<HTMLElement>(selector)
  if (direct) return direct
  // Отключённая кнопка MUI не принимает клики (pointer-events: none) —
  // событие приходит на обёртку-span, внутри которой кнопка лежит.
  if (target.tagName === 'SPAN') return target.querySelector<HTMLElement>(selector)
  return null
}

export function InterceptClicks({ rules, children }: { rules: InterceptRule[]; children: ReactNode }) {
  const onClickCapture = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    for (const rule of rules) {
      const hit = findHit(target, rule.selector)
      if (hit) {
        event.stopPropagation()
        event.preventDefault()
        rule.handle(hit)
        return
      }
    }
  }
  return (
    <div style={{ display: 'contents' }} onClickCapture={onClickCapture}>
      {children}
    </div>
  )
}
