import { useEffect, useRef } from 'react'

/**
 * Нумерованные рамки поверх макета — то, что видно на картинках в статьях.
 *
 * Координаты не подбираются на глаз и не ищутся по цвету пикселей. Мы просим
 * сам элемент назвать свой прямоугольник (`getBoundingClientRect`) и кладём
 * рамку ровно по нему. Значит, рамка не может «уехать» от кнопки при
 * перевёрстке экрана: съехать ей физически некуда, она берётся из той же
 * разметки, что и кнопка.
 *
 * Меряем и раскладываем рамки на каждом кадре, а не один раз после загрузки, и
 * пишем координаты прямо в стиль узла, минуя состояние React. Это не
 * микрооптимизация, а единственный способ не промахнуться: экран дорисовывается
 * рывками (приходят данные, встают шрифты, асинхронно собирается макет
 * этикетки), и последний такой рывок случается ровно в тот момент, когда
 * безголовый браузер снимает кадр. Замер по таймеру этот рывок не догоняет —
 * проверено: рамка вставала на девяносто пикселей выше кнопки «Печать».
 * Пересчёт в `requestAnimationFrame` идёт перед каждой отрисовкой, поэтому
 * попадает в кадр всегда.
 *
 * Селекторы приходят в адресе страницы: `?scene=…&mark=<селектор>|<селектор>`.
 * Почти везде в портале проставлены `data-testid` — их и указываем.
 */

const ACCENT = '#f2622a'

/**
 * Первый ВИДИМЫЙ элемент по селектору.
 *
 * Простого `querySelector` мало: MUI держит закрытые диалоги и свёрнутые панели
 * в дереве, и по тому же `data-testid` первой находится кнопка из невидимого
 * окна. Рамка тогда ложится в пустоту — ровно та ошибка, ради которой всё это
 * и делалось.
 */
function firstVisible(selector: string): HTMLElement | null {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>(selector))
  for (const element of candidates) {
    if (element.offsetParent === null && getComputedStyle(element).position !== 'fixed') continue
    const rect = element.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) continue
    if (rect.bottom <= 0 || rect.right <= 0) continue
    return element
  }
  return null
}

export function SceneMarkers({ selectors }: { selectors: string[] }) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host || selectors.length === 0) return

    // Узлы рамок создаём один раз и дальше только двигаем.
    const nodes = selectors.map((_, index) => {
      const box = document.createElement('div')
      box.style.cssText = [
        'position:absolute',
        'z-index:3000',
        'pointer-events:none',
        `border:3px solid ${ACCENT}`,
        'border-radius:10px',
        'display:none',
      ].join(';')
      const badge = document.createElement('div')
      badge.textContent = String(index + 1)
      badge.style.cssText = [
        'position:absolute',
        'left:-13px',
        'top:-13px',
        'width:26px',
        'height:26px',
        'border-radius:50%',
        `background:${ACCENT}`,
        'color:#fff',
        'font:700 14px/26px system-ui,-apple-system,sans-serif',
        'text-align:center',
      ].join(';')
      box.appendChild(badge)
      host.appendChild(box)
      return box
    })

    let frame = 0
    const tick = () => {
      selectors.forEach((selector, index) => {
        const node = nodes[index]
        if (!node) return
        const element = firstVisible(selector)
        if (!element) {
          node.style.display = 'none'
          return
        }
        const rect = element.getBoundingClientRect()
        node.style.display = 'block'
        node.style.left = `${rect.left + window.scrollX - 6}px`
        node.style.top = `${rect.top + window.scrollY - 6}px`
        node.style.width = `${rect.width + 12}px`
        node.style.height = `${rect.height + 12}px`
      })
      frame = window.requestAnimationFrame(tick)
    }
    tick()

    return () => {
      window.cancelAnimationFrame(frame)
      nodes.forEach((node) => node.remove())
    }
  }, [selectors])

  return <div ref={hostRef} />
}
