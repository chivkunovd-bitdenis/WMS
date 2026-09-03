import { useState } from 'react'

import { SortingObjectsScreen } from '../../sorting-objects/SortingObjectsScreen'
import { FfWarehouseMapScreen } from '../../warehouse-map/FfWarehouseMapScreen'
import type { MapRow } from '../../warehouse-map/WarehouseMapRows'
import type { MoveIntent } from '../../warehouse-map/WarehouseMapMoveDialog'
import type { WarehouseMapData } from '../../warehouse-map/WarehouseMapTypes'
import { addCell, addWarehouse, applyIntent, stubData } from '../../warehouse-map/stub'
import { SceneShell } from './SceneShell'

/**
 * Два узла складского процесса: разложить принятое и посмотреть, где что лежит.
 *
 * Оба экрана уже умеют жить без сервера — у них есть свои выдуманные данные
 * (`sorting-objects/objectsStub.ts` и `warehouse-map/stub.ts`), теми же
 * пользуются обычные превью `/sorting-objects.html` и `/warehouse-map.html`.
 * Здесь мы берём ровно те же данные и те же компоненты, но заворачиваем их в
 * настоящий шелл портала: на картинке в статье должно быть видно шапку и левое
 * меню, иначе сотрудник не поймёт, куда ему идти за этим экраном.
 */

/** От чьего имени пишется журнал перемещений в макете. */
const ACTOR = 'Смирнова Ольга'

/**
 * Раскладка принятого товара по ячейкам.
 *
 * Экран берёт данные из `objectsStub`: дерево коробов и грузомест, товары
 * внутри них, поле сканера и поле ячейки для размещения. Ни один проп с
 * данными не передаём намеренно — так макет остаётся ровно тем же, что и
 * рабочее превью экрана, и не разъезжается с ним при правках.
 *
 * `onNote` обязателен: экран сообщает наверх, что произошло. В макете отвечать
 * на это некому и незачем — подсказки печатала бы лента превью, а её на
 * картинке в статье быть не должно.
 */
export function SortingScene() {
  return (
    <SceneShell route="/app/ff/sorting">
      <SortingObjectsScreen
        onNote={() => {}}
        warehouseName="Ярцево"
        purpose="Приёмка № 000045 от 03.09.2026. Собираем объект и ставим готовый объект на полку."
      />
    </SceneShell>
  )
}

/**
 * Карта склада: зоны, стеллажи, ячейки и остаток на каждой.
 *
 * Данные держим в состоянии, а не константой, чтобы макет отвечал на действия:
 * перетаскивание строки на другую ячейку, заведение ячейки и склада работают
 * так же, как на живом экране. Для статьи это важнее, чем кажется — картинки
 * снимаются со страницы, которую перед съёмкой можно довести руками до нужного
 * состояния.
 */
export function WarehouseMapScene() {
  const [warehouseId, setWarehouseId] = useState('wh-yartsevo')
  const [data, setData] = useState<WarehouseMapData>(() => stubData('wh-yartsevo'))

  return (
    <SceneShell route="/app/ff/warehouse-map">
      <FfWarehouseMapScreen
        data={data}
        loading={false}
        error={null}
        warehouseId={warehouseId}
        onWarehouseChange={(nextId) => {
          setWarehouseId(nextId)
          setData(stubData(nextId))
        }}
        onMove={(intent: MoveIntent, qty) => {
          setData((current) =>
            applyIntent(
              current,
              {
                reason: intent.reason,
                rowKey: intent.row.key,
                rowTitle: intent.row.title,
                fromLabel: intent.fromLabel,
                toKey: intent.toKey,
                toLabel: intent.toLabel,
              },
              qty,
              ACTOR,
            ),
          )
        }}
        onCreateCell={(code) => setData((current) => addCell(current, code))}
        onCreateWarehouse={(name) => setData((current) => addWarehouse(current, name))}
        // Принтера под макетом нет, а окно печати закрывается само: показывать
        // на картинке ошибку «не удалось напечатать» было бы враньём.
        onPrintCell={() => {}}
        // Пересчёт — отдельная сцена (`inventory-count`), сюда его не тянем.
        onInventory={() => {}}
        historyFor={(row: MapRow) => data.journal.filter((entry) => entry.subject === row.title)}
      />
    </SceneShell>
  )
}
