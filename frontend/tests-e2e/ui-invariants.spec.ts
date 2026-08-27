import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const INVARIANTS_SOURCE = readFileSync(
  new URL('../../scripts/ui/invariants.js', import.meta.url),
  'utf8',
)

type Violation = { rule: string; what: string; sample: string }

async function invariants(page: Page, body: string) {
  await page.setContent(`<style>html, body { margin: 0; }</style>${body}`)
  return JSON.parse(await page.evaluate((source) => eval(source), INVARIANTS_SOURCE)) as {
    ok: boolean
    violations: Violation[]
  }
}

function rules(result: { violations: Violation[] }) {
  return result.violations.map((violation) => violation.rule)
}

test('ui invariants permit only a reachable DataTable horizontal scroll inside its card', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 300 })
  const result = await invariants(page, `
    <div class="MuiPaper-root MuiTableContainer-root" style="position:relative;width:160px;overflow-x:auto">
      <table style="width:400px"><tbody><tr><td><button class="MuiButton-root" style="margin-left:300px">Действие</button></td></tr></tbody></table>
    </div>
  `)

  expect(rules(result)).not.toContain('R-01')
  expect(rules(result)).not.toContain('R-08')
})

test('ui invariants keep R-08 for hidden or non-overflowing DataTable content', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 300 })
  const hidden = await invariants(page, `
    <div class="MuiPaper-root MuiTableContainer-root" style="position:relative;width:160px;overflow-x:hidden">
      <button class="MuiButton-root" style="position:absolute;left:240px">Скрыто</button>
    </div>
  `)
  const noOverflow = await invariants(page, `
    <div class="MuiPaper-root MuiTableContainer-root" style="margin-left:200px;position:relative;width:160px;overflow-x:auto">
      <button class="MuiButton-root" style="position:relative;left:-100px">Не достижимо</button>
    </div>
  `)

  expect(rules(hidden)).toContain('R-08')
  expect(rules(noOverflow)).toContain('R-08')
})

test('ui invariants keep R-08 when the scrollport is outside the current card', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 300 })
  const result = await invariants(page, `
    <div class="MuiTableContainer-root" style="width:160px;overflow-x:auto">
      <div class="MuiPaper-root" style="position:relative;width:160px;overflow:visible">
        <button class="MuiButton-root" style="position:absolute;left:240px">Вне карточки</button>
      </div>
    </div>
  `)

  expect(rules(result)).toContain('R-08')
})

test('ui invariants permit a DataTable endpoint still visible through a wide intermediate clip', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 300 })
  const result = await invariants(page, `
    <div class="MuiPaper-root MuiTableContainer-root" style="position:relative;width:160px;overflow-x:auto">
      <div style="width:400px;overflow-x:hidden">
        <button class="MuiButton-root" style="margin-left:300px">Обрезано внутри</button>
      </div>
    </div>
  `)

  expect(rules(result)).not.toContain('R-08')
})

test('ui invariants keep R-08 when an intermediate clip crops every DataTable endpoint', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 300 })
  const result = await invariants(page, `
    <div class="MuiPaper-root MuiTableContainer-root" style="position:relative;width:160px;overflow-x:auto">
      <table style="width:400px"><tbody><tr><td>
        <div style="width:160px;overflow-x:hidden">
          <button class="MuiButton-root" style="margin-left:300px">Обрезано внутри</button>
        </div>
      </td></tr></tbody></table>
    </div>
  `)

  expect(rules(result)).toContain('R-08')
})

test('ui invariants retain R-01 and R-09 for page overflow and overlapping table columns', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 300 })
  const result = await invariants(page, `
    <div style="width:480px;height:1px"></div>
    <table><tbody><tr><td style="width:120px">Первый</td><td style="position:relative;left:-80px;width:120px">Второй</td></tr></tbody></table>
  `)

  expect(rules(result)).toContain('R-01')
  expect(rules(result)).toContain('R-09')
})
