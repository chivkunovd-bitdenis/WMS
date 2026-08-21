import { describe, expect, it } from 'vitest'
import { isAutoFbsWarehouse, primaryWarehouseId, realWarehouses } from './fbsWarehouse'

const osnovnoy = { id: 'wh-1', name: 'Основной', code: 'main' }
const fbsShadow = { id: 'wh-2', name: 'FBS WB 1887957', code: 'fbs-wb-1887957' }
const secondReal = { id: 'wh-3', name: 'Склад на Даниловской', code: 'danilovskaya' }

describe('isAutoFbsWarehouse', () => {
  it('распознаёт склад-подстановку по коду', () => {
    expect(isAutoFbsWarehouse(fbsShadow)).toBe(true)
  })

  it('не считает настоящий склад подстановкой', () => {
    expect(isAutoFbsWarehouse(osnovnoy)).toBe(false)
  })
})

describe('realWarehouses', () => {
  it('убирает автосозданные склады WB из списка', () => {
    expect(realWarehouses([fbsShadow, osnovnoy])).toEqual([osnovnoy])
  })

  it('не трогает список, если подстановок нет', () => {
    expect(realWarehouses([osnovnoy, secondReal])).toEqual([osnovnoy, secondReal])
  })
})

describe('primaryWarehouseId', () => {
  it('берёт первый настоящий склад, даже если подстановка идёт по алфавиту раньше', () => {
    // "FBS WB …" на латинице сортируется раньше кириллического «Основной» — именно
    // так 20.08 заявка на приёмку молча уехала не в тот склад (I10).
    expect(primaryWarehouseId([fbsShadow, osnovnoy])).toBe(osnovnoy.id)
  })

  it('не ломается, если реальных складов нет вовсе', () => {
    expect(primaryWarehouseId([fbsShadow])).toBe(fbsShadow.id)
  })

  it('возвращает null для пустого списка', () => {
    expect(primaryWarehouseId([])).toBeNull()
  })
})
