import { describe, expect, it } from 'vitest'

import { restoreCisGs } from './restoreCisGs'

// Те же векторы, что и в backend/tests/test_fbs_kiz.py (I3), чтобы клиентская
// и серверная реализация были доказуемо согласованы на одних и тех же примерах.
const GS = '\x1d'
const GTIN = '04606012345678'
const SIGNATURE_44 = 'MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY='
const SIGNATURE_88 = 'MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo90000'

function cis(serial: string, verification: string, signature: string, withGs: boolean): string {
  const sep = withGs ? GS : ''
  return `01${GTIN}21${serial}${sep}91${verification}${sep}92${signature}`
}

describe('restoreCisGs', () => {
  it('restores separators for a clothing signature (44 chars)', () => {
    const glued = cis('aXq7Tz9Km', 'K7pQ', SIGNATURE_44, false)
    const expected = cis('aXq7Tz9Km', 'K7pQ', SIGNATURE_44, true)

    const result = restoreCisGs(glued)

    expect(result).toEqual({ value: expected, restored: true, unrestorable: false })
  })

  it('restores separators for a footwear signature (88 chars)', () => {
    const glued = cis('Zk9L2pQ1', 'M3xR', SIGNATURE_88, false)
    const expected = cis('Zk9L2pQ1', 'M3xR', SIGNATURE_88, true)

    const result = restoreCisGs(glued)

    expect(result).toEqual({ value: expected, restored: true, unrestorable: false })
  })

  it('is not fooled by "91"/"92" occurring inside the serial number', () => {
    // Главная ловушка задачи: наивный поиск подстроки "91"/"92" принял бы эти
    // символы внутри серийника за начало служебных блоков и обрезал бы код
    // посреди значения. Разбор по фиксированным смещениям от конца строки
    // должен найти настоящие маркеры, а не эти.
    const trapSerial = 'A91XB92YC7z'
    const glued = cis(trapSerial, 'Q9zK', SIGNATURE_44, false)
    const expected = cis(trapSerial, 'Q9zK', SIGNATURE_44, true)

    const result = restoreCisGs(glued)

    expect(result).toEqual({ value: expected, restored: true, unrestorable: false })
    expect(result.value).toContain(trapSerial)
  })

  it('leaves an already-separated code untouched', () => {
    const alreadyOk = cis('aXq7Tz9Km', 'K7pQ', SIGNATURE_44, true)

    const result = restoreCisGs(alreadyOk)

    expect(result).toEqual({ value: alreadyOk, restored: false, unrestorable: false })
  })

  it('leaves a short-form CIS without the crypto tail untouched', () => {
    // Короткий КИЗ без криптохвоста — валидный формат WB (см.
    // verify-product-identifiers.md, «Короткий и длинный КИЗ»). У него нет
    // 91/92 и не нужен разделитель перед последним полем — это не дефект.
    const shortForm = `01${GTIN}21SHORT1234`

    const result = restoreCisGs(shortForm)

    expect(result).toEqual({ value: shortForm, restored: false, unrestorable: false })
  })

  it('flags an unrestorable code instead of guessing', () => {
    // Подпись обрублена — длина хвоста не подходит ни под одежду (44), ни под
    // обувь (88). Значение возвращается БЕЗ ИЗМЕНЕНИЙ, чтобы битый код точно
    // не ушёл в WB как будто он в порядке.
    const glued = cis('aXq7Tz9Km', 'K7pQ', SIGNATURE_44, false)
    const broken = glued.slice(0, -5)

    const result = restoreCisGs(broken)

    expect(result).toEqual({ value: broken, restored: false, unrestorable: true })
  })

  it('ignores values that do not look like a CIS at all', () => {
    const result = restoreCisGs('*DUIkWJJF')

    expect(result).toEqual({ value: '*DUIkWJJF', restored: false, unrestorable: false })
  })
})
