import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ScannerLine } from './ScannerLine'

describe('ScannerLine', () => {
  it('говорит, что слушает, и чего именно ждёт', () => {
    const markup = renderToStaticMarkup(
      <ScannerLine active expects="ШК ячейки, тары или товара" testId="inv-scan-line" />,
    )

    expect(markup).toContain('data-scanner-active="true"')
    expect(markup).toContain('Сканер активен — ШК ячейки, тары или товара')
  })

  it('не слушает — говорит об этом и зовёт нажать', () => {
    // Раньше плашка горела зелёным всегда. Оператор трогал соседнее поле, фокус
    // уходил, «клавиатурный» сканер печатал штрихкод туда — на прод-документе
    // код 4630452735395 уехал в «Комментарий», — а экран продолжал обещать, что
    // сканер работает. Молчаливая потеря пика на складе читается как «система
    // сломалась», и оператор бросает пересчёт.
    const markup = renderToStaticMarkup(
      <ScannerLine active={false} expects="товар в коробе КР-000108" testId="inv-scan-line" />,
    )

    expect(markup).toContain('data-scanner-active="false"')
    expect(markup).toContain('Сканер не слушает — нажмите сюда и пикайте снова')
    expect(markup).not.toContain('Сканер активен')
  })
})
