import { useEffect, useState } from 'react'

type Rect = Pick<DOMRect, 'left' | 'right' | 'top' | 'bottom' | 'width' | 'height'>

// Keep the global button clear of existing fixed/sticky action bars without modifying those screens.
export function helpButtonBottom(width: number, height: number, controls: Rect[]): number {
  const size = 40
  const right = width - 16
  const left = right - size
  let bottom = 16
  for (let step = 0; step <= controls.length; step++) {
    const top = height - bottom - size
    const hit = controls.find((rect) => rect.width > 0 && rect.height > 0 && rect.left < right + 8 && rect.right > left - 8 && rect.top < top + size + 8 && rect.bottom > top - 8)
    if (!hit) break
    bottom = height - hit.top + 12
  }
  return Math.min(bottom, Math.max(16, height - size - 16))
}

export function useHelpButtonBottom(): number {
  const [bottom, setBottom] = useState(16)
  useEffect(() => {
    const content = document.querySelector('[data-testid="app-content"]')
    if (!content) return
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const controls = [...content.querySelectorAll('button, a, input, select, textarea, [role="button"]')].map((node) => node.getBoundingClientRect())
        setBottom(helpButtonBottom(document.documentElement.clientWidth || window.innerWidth, window.innerHeight, controls))
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
  }, [])
  return bottom
}
