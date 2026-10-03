import { useEffect, useState } from 'react'

/**
 * WMS-649 · «места подключения» для единственного нового элемента макета.
 *
 * Экраны и окна продукта в макете настоящие и не правятся. Новый элемент (выбор
 * площадки в окне печати, выбор ШК по умолчанию в карточке товара) встаёт в
 * них через портал: хук находит нужный узел настоящего окна и заводит рядом свой
 * контейнер. Окно закрылось — узел исчез, контейнер пропал вместе с ним, при
 * следующем открытии хук заведёт новый.
 */

export type HostPlacement = 'first-child' | 'after'

export type HostSpec = {
  /** Уникальный ключ контейнера. */
  id: string
  /** Селектор узла, относительно которого ставим контейнер. */
  selector: string
  placement: HostPlacement
  /** Скрыть найденный узел, пока контейнер на месте (замена значения на элемент). */
  hideTarget?: boolean
}

function ensureHost(spec: HostSpec): HTMLElement | null {
  const target = document.querySelector<HTMLElement>(spec.selector)
  if (!target) return null
  const attr = `data-wms649-host`
  if (spec.placement === 'first-child') {
    const found = target.querySelector<HTMLElement>(`:scope > [${attr}="${spec.id}"]`)
    if (found) return found
    const host = document.createElement('div')
    host.setAttribute(attr, spec.id)
    target.insertBefore(host, target.firstChild)
    return host
  }
  const next = target.nextElementSibling
  if (next instanceof HTMLElement && next.getAttribute(attr) === spec.id) return next
  const host = document.createElement('div')
  host.setAttribute(attr, spec.id)
  host.style.gridColumn = '2'
  target.after(host)
  if (spec.hideTarget) target.style.display = 'none'
  return host
}

/** Следит за DOM и отдаёт контейнер, пока узел-цель существует. */
export function useHost(spec: HostSpec | null): HTMLElement | null {
  const [host, setHost] = useState<HTMLElement | null>(null)
  const key = spec ? `${spec.id}|${spec.selector}|${spec.placement}|${spec.hideTarget ? 1 : 0}` : ''

  useEffect(() => {
    if (!spec) {
      setHost(null)
      return
    }
    const sync = () => {
      const next = ensureHost(spec)
      setHost((prev) => (prev === next ? prev : next))
    }
    sync()
    const observer = new MutationObserver(sync)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      observer.disconnect()
      // Оверлей снят («Сейчас»): возвращаем экран продукта ровно как был.
      document.querySelectorAll<HTMLElement>(`[data-wms649-host="${spec.id}"]`).forEach((node) => {
        const previous = node.previousElementSibling
        if (previous instanceof HTMLElement && previous.style.display === 'none') {
          previous.style.display = ''
        }
        node.remove()
      })
      setHost(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return host
}

/** Читает текст узла (для опознания товара по заголовку окна). */
export function useNodeText(selector: string, deps: unknown): string {
  const [text, setText] = useState('')
  useEffect(() => {
    const sync = () => {
      const next = document.querySelector(selector)?.textContent ?? ''
      setText((prev) => (prev === next ? prev : next))
    }
    sync()
    const observer = new MutationObserver(sync)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [selector, deps])
  return text
}

/** Выставляет значение MUI-select через его скрытый нативный input, как это делают тесты. */
export function setNativeSelectValue(root: ParentNode, selectTestId: string, value: string): boolean {
  const input = root.querySelector<HTMLInputElement>(
    `[data-testid="${selectTestId}"] input.MuiSelect-nativeInput`,
  )
  if (!input) return false
  if (input.value === value) return true
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}
