import { useEffect } from 'react'

import { UnloadPickScreen } from '../../unload-pick/UnloadPickScreen'
import { SceneShell } from './SceneShell'

/**
 * Подбор товара под отгрузку на маркетплейс.
 *
 * Узловой шаг статьи про отгрузку: план по позициям, где каждая строка знает,
 * сколько надо собрать и из каких мест это снимать — с палеты, из короба, из
 * грузоместа или прямо с ячейки. Экран уже умеет работать без сервера: план,
 * остатки, тара и ячейки лежат в `unload-pick/pickStub.ts`, и то же самое
 * показывает обычное превью `/unload-pick.html`.
 *
 * Ни одного пропа с данными не передаём: макет обязан совпадать с рабочим
 * превью экрана до строчки, иначе картинка в инструкции начнёт расходиться с
 * тем, что сотрудник видит на работе.
 */
export function UnloadPickScene() {
  /**
   * Раскрываем первую позицию плана.
   *
   * Статья объясняет подбор по ячейкам, а свёрнутая строка отвечает на это
   * только словами «В 4 местах» — самих ячеек, тары и полей количества не
   * видно, и картинка не показывает того, ради чего сделана. Раскрывашка —
   * внутреннее состояние экрана, пропом снаружи не задаётся, поэтому нажимаем
   * ту же кнопку, что нажал бы человек. Ищем по префиксу `data-testid`, а не по
   * конкретному номеру строки: состав выдуманного плана правится в чужом файле,
   * и привязка к его первой позиции сломалась бы молча.
   */
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.querySelector('[data-testid^="pick-table-expanded-"]')) {
        window.clearInterval(timer)
        return
      }
      const button = document.querySelector<HTMLElement>('[data-testid^="pick-table-expand-"]')
      if (button) button.click()
    }, 120)
    // Сдаёмся через несколько секунд: вечный таймер в макете хуже, чем
    // свёрнутая строка.
    const stop = window.setTimeout(() => window.clearInterval(timer), 5000)
    return () => {
      window.clearInterval(timer)
      window.clearTimeout(stop)
    }
  }, [])

  return (
    <SceneShell route="/app/ff/mp-shipments">
      {/* `onNote` — единственный обязательный проп: экран рассказывает наверх,
          что сделал оператор. В макете эти подсказки печатать некуда: лента
          превью на картинку в статье попадать не должна. */}
      <UnloadPickScreen onNote={() => {}} />
    </SceneShell>
  )
}
