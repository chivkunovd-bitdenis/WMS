import { useState } from 'react'

import { FfInventoryCountScreen } from '../../inventory/FfInventoryCountScreen'
import { FfInventoryListScreen } from '../../inventory/FfInventoryListScreen'
import type { InventoryCount } from '../../inventory/InventoryTypes'
import { stubCount, stubList } from '../../inventory/stub'
import { SceneShell } from './SceneShell'

/**
 * Номера документов пересчёта в общем стабе стилизованы под сквозную нумерацию
 * («ИНВ-000124»), а сервер выдаёт другое: `ИНВ-` плюс первый кусок UUID
 * заглавными — см. `backend/app/api/inventory_counts.py`. Для превью разница
 * неважна, а для инструкции важна: сотрудник должен искать на экране то, что
 * там правда написано. Поэтому в макетах базы знаний номера подменяем на
 * настоящий формат, не трогая общий стаб — он кормит ещё и `/inventory.html`.
 */
const REAL_NUMBERS = ['ИНВ-3F2A9C11', 'ИНВ-8B41D07E', 'ИНВ-A15C62F3', 'ИНВ-6D9E4B20', 'ИНВ-24F7C8A5']

function withRealNumbers<T extends { number: string }>(rows: T[]): T[] {
  return rows.map((row, index) => ({ ...row, number: REAL_NUMBERS[index] ?? row.number }))
}

/**
 * Инвентаризация: список документов пересчёта и открытый документ.
 *
 * Оба экрана уже presentational — данные приходят пропсами, сервер им не нужен.
 * Выдуманные документы берём из `inventory/stub.ts`, того же, что кормит
 * обычное превью `/inventory.html`: там уже подобраны интересные случаи —
 * посчитанные строки, непосчитанные, излишек и недостача. Придумывать второй
 * набор данных значило бы разводить две правды об одном экране.
 */

/**
 * Список документов пересчёта — состояние «Список документов» из превью.
 *
 * Кнопки живые, но вести им некуда: сцена показывает один шаг процесса, а не
 * работающий портал. Открытый документ — это соседняя сцена `inventory-count`.
 */
export function InventoryListScene() {
  return (
    <SceneShell route="/app/ff/stocktaking">
      <FfInventoryListScreen
        items={withRealNumbers(stubList())}
        loading={false}
        onOpen={() => {}}
        onCreate={() => {}}
      />
    </SceneShell>
  )
}

/**
 * Открытый документ пересчёта в черновике.
 *
 * Состав держим в состоянии: сотрудник на картинке видит поле «факт», и оно
 * должно заполняться по-настоящему, если сцену открыть и потрогать руками —
 * и сканером тоже, поле сканера у экрана своё. Сохранение и проведение
 * оставлены пустыми: без сервера они могли бы только сделать вид, а показывать
 * в инструкции кнопку, которая врёт, нельзя.
 */
export function InventoryCountScene() {
  const [count, setCount] = useState<InventoryCount>(() => ({
    ...stubCount(),
    number: REAL_NUMBERS[0] ?? 'ИНВ-3F2A9C11',
  }))

  return (
    <SceneShell route="/app/ff/stocktaking">
      <FfInventoryCountScreen
        count={count}
        loading={false}
        error={null}
        note={null}
        onChange={setCount}
        onSave={() => {}}
        onPost={() => {}}
        onCancelDocument={() => {}}
        // Без этого пропа три кнопки «Создать короб / палету / грузоместо»
        // гаснут с подсказкой «Создание тары недоступно». На рабочем экране
        // они живые (`FfInventoryPage` их подключает), и картинка в инструкции
        // не должна показывать сотруднику запрет, которого на деле нет.
        onCreateContainer={() => {}}
        onBack={() => {}}
      />
    </SceneShell>
  )
}
