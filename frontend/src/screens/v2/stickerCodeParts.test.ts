import { describe, expect, it } from 'vitest'
import { stickerCodeParts } from './FfFbsSupplyWorkspace'

describe('номер стикера WB на упаковке', () => {
  it('делит человеческий номер по пробелу: хвост печатается крупно', () => {
    expect(stickerCodeParts('5694425 3074')).toEqual({ head: '5694425', tail: '3074' })
  })

  it('слитный номер делит по последним четырём знакам — это тот же partB', () => {
    expect(stickerCodeParts('56944253074')).toEqual({ head: '5694425', tail: '3074' })
  })

  it('короткий номер целиком считает хвостом, а не режет в пустоту', () => {
    expect(stickerCodeParts('307')).toEqual({ head: '', tail: '307' })
  })

  it('пустой стикер — это отсутствие номера, а не пустые части', () => {
    expect(stickerCodeParts(null)).toBeNull()
    expect(stickerCodeParts('   ')).toBeNull()
  })
})
