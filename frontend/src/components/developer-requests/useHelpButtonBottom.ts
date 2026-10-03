import { useEffect, useState } from 'react'

type Rect = Pick<DOMRect, 'left' | 'right' | 'top' | 'bottom' | 'width' | 'height'>

// Offsets of the button's resting place from the viewport's lower right corner.
export type HelpButtonCorner = { right: number; bottom: number }
export const DEFAULT_HELP_BUTTON_CORNER: HelpButtonCorner = { right: 16, bottom: 16 }

// Keep the global button clear of existing fixed/sticky action bars without modifying those screens.
export function helpButtonBottom(
  width: number,
  height: number,
  controls: Rect[],
  corner: HelpButtonCorner = DEFAULT_HELP_BUTTON_CORNER,
): number {
  const size = 40
  const right = width - corner.right
  const left = right - size
  let bottom = corner.bottom
  for (let step = 0; step <= controls.length; step++) {
    const top = height - bottom - size
    const hit = controls.find((rect) => rect.width > 0 && rect.height > 0 && rect.left < right + 8 && rect.right > left - 8 && rect.top < top + size + 8 && rect.bottom > top - 8)
    if (!hit) break
    bottom = height - hit.top + 12
  }
  return Math.min(bottom, Math.max(corner.bottom, height - size - 16))
}

export function useHelpButtonBottom(corner: HelpButtonCorner = DEFAULT_HELP_BUTTON_CORNER): number {
  const { right: cornerRight, bottom: cornerBottom } = corner
  const [bottom, setBottom] = useState(cornerBottom)
  useEffect(() => {
    const content = document.querySelector('[data-testid="app-content"]')
    if (!content) return
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const controls = [...content.querySelectorAll('button, a, input, select, textarea, [role="button"]')].map((node) => node.getBoundingClientRect())
        setBottom(helpButtonBottom(document.documentElement.clientWidth || window.innerWidth, window.innerHeight, controls, { right: cornerRight, bottom: cornerBottom }))
      })
    }
    const mutations = new MutationObserver(update)
    mutations.observe(content, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style', 'hidden'] })
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    resize?.observe(content)
    window.addEventListener('resize', update)
    document.addEventListener('scroll', update, true)
    update()
    return () => {
      cancelAnimationFrame(frame); mutations.disconnect(); resize?.disconnect()
      window.removeEventListener('resize', update); document.removeEventListener('scroll', update, true)
    }
  }, [cornerRight, cornerBottom])
  return bottom
}
