// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { Dialog } from '@mui/material'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { FfSortingObjectsPage } from './FfSortingObjectsPage'
import {
  CELLS,
  DOC_A,
  FakeSortingServer,
  TOKEN_1,
  WAREHOUSE_ID,
  click,
  installFetch,
  must,
  placedCellHeader,
  prepareDom,
  resetStorage,
  scannerInput,
  settle,
} from './wms650TestKit'

// WMS-650 · приёмка: в продукте экран раскладки открыт внутри окна документа
// приёмки (MUI Dialog, role="dialog"). После окна «Куда положить» — и после
// «Положить», и после «Отмена» — сканер снова слушает: фокус в поле сканера.
// Окно документа, внутри которого стоит сам экран, «другим окном» не считается.

beforeAll(() => {
  prepareDom()
})

let root: Root | null = null
let host: HTMLDivElement | null = null
let restoreFetch: () => void = () => undefined

function mountInDocumentDialog() {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => {
    root!.render(
      createElement(
        MemoryRouter,
        null,
        createElement(
          Dialog,
          { open: true, fullScreen: true, 'aria-label': 'Документ приёмки' },
          createElement(FfSortingObjectsPage, {
            token: TOKEN_1,
            warehouses: [{ id: WAREHOUSE_ID, name: 'Ярцево' }],
            embedded: true,
            inboundRequestId: DOC_A,
            onPlaced: async () => undefined,
          }),
        ),
      ),
    )
  })
}

beforeEach(() => {
  resetStorage()
})

afterEach(() => {
  if (root) act(() => root!.unmount())
  host?.remove()
  root = null
  host = null
  restoreFetch()
  document.body.innerHTML = ''
  resetStorage()
})

async function openPlusAndLeaveScanner() {
  await click(placedCellHeader(CELLS.a11))
  const plus = must('objects-tree-place-o-k3')
  act(() => {
    scannerInput().focus()
    plus.focus()
  })
  expect(document.activeElement).not.toBe(scannerInput())
  await click(plus)
}

describe('WMS-650 · экран внутри окна документа: фокус после «Куда положить»', () => {
  it('после «Положить» фокус в поле сканера', async () => {
    const server = new FakeSortingServer()
    restoreFetch = installFetch(server)
    mountInDocumentDialog()
    await settle()
    expect(scannerInput().closest('[role="dialog"]')).not.toBeNull()
    await openPlusAndLeaveScanner()
    await click(must('objects-qty-confirm'))
    await settle(80)
    expect(server.requests('place')).toHaveLength(1)
    expect(document.activeElement).toBe(scannerInput())
  })

  it('после «Отмена» фокус в поле сканера', async () => {
    const server = new FakeSortingServer()
    restoreFetch = installFetch(server)
    mountInDocumentDialog()
    await settle()
    await openPlusAndLeaveScanner()
    await click(must('objects-qty-cancel'))
    await settle(80)
    expect(server.requests('place')).toHaveLength(0)
    expect(document.activeElement).toBe(scannerInput())
  })
})
