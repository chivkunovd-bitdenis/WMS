/* eslint-disable react-refresh/only-export-components -- файл описывает формы макета: рядом с компонентами экспортируется список FORMS, горячая перезагрузка здесь не нужна */
import { useState, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Box, CssBaseline, ThemeProvider } from '@mui/material'

import { FfProductsCatalogScreen } from '../../screens/v2/FfProductsCatalogScreen'
import { FfFbsSupplyWorkspace } from '../../screens/v2/FfFbsSupplyWorkspace'
import { FfInboundRequestView } from '../../screens/ff/FfInboundRequestView'
import { FfPackagingPage } from '../../screens/ff/FfPackagingPage'
import { FfHonestSignPage } from '../../screens/ff/FfHonestSignPage'
import { SceneShell } from '../../screens/ff/knowledge/scenes/SceneShell'
import { SellerInboundDraftScreen } from '../../screens/v2/SellerInboundDraftScreen'
import { ProductBarcodePrintDialog } from '../../components/ProductBarcodePrintDialog'
import { AuthedAppLayout } from '../../layouts/AuthedAppLayout'
import { muiTheme } from '../../mui/theme'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'
import { printInboundReceivingSheet } from '../../utils/printInboundReceivingSheet'
import { printShipmentPackagingSheet } from '../../utils/printShipmentPackagingSheet'
import { displayMetaToProductLabel } from '../../utils/productBarcodePrint'
import {
  catalogRowToDisplayMeta,
  resolveProductBarcodeOptions,
  type ProductLineDisplayMeta,
} from '../../types/wbProductCatalog'
import { InterceptClicks } from './Intercept'
import { MarkingDialogOverlay, ProductCardOverlay, ProductDialogOverlay } from './overlays'
import { platformsOf } from './platforms'
import type { DemoProduct, Marketplace } from './products'
import { catalogFields, DEMO_SELLER, getDefaultCode, PRODUCTS, productById } from './products'
import { WAREHOUSE } from './routes'
import { MOCK_TOKEN } from './runtime'
import {
  INBOUND_IDS,
  inboundProducts,
  inboundRoutes,
  receivingSheetItems,
  type InboundVariant,
} from './routesInbound'
import { PACKAGING_IDS, PACKAGING_QTY, packagingProducts, packagingRoutes } from './routesPackaging'
import { fbsRoutes, fbsSupplyId, type FbsStage } from './routesFbs'
import { honestSignRoutes } from './routesHonestSign'
import type { StubRoute } from '../../screens/ff/knowledge/scenes/stubFetch'

/** Режим макета: «Сейчас» — настоящее поведение продукта, «Предложение» — с выбором площадки. */
export type MockMode = 'now' | 'proposal'

export type FormCtx = {
  mode: MockMode
  /** Площадка документа для форм с переключателем «Документ: WB | Ozon». */
  doc: Marketplace
}

export type FormDef = {
  id: string
  title: string
  /** Где форма живёт в интерфейсе. */
  where: string
  /** Известна ли площадка из документа, в котором печатают. */
  platformKnown: 'нет' | 'да' | 'зависит от документа'
  /** Показывать переключатель «Документ: WB | Ozon». */
  docToggle: boolean
  /** Что нажать. */
  hint: string
  /** Эмулятор сканера: коды, которые можно «отсканировать» в этой форме. */
  scanCodes?: (doc: Marketplace) => Array<{ label: string; code: string }>
  routes: StubRoute[]
  render: (ctx: FormCtx) => ReactNode
}

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

function CatalogScreen() {
  return (
    <SceneShell route="/app/ff/products">
      <FfProductsCatalogScreen
        token={MOCK_TOKEN}
        authHeaders={authHeaders}
        sellers={[DEMO_SELLER]}
        warehouses={[WAREHOUSE]}
        canManageCatalog
      />
    </SceneShell>
  )
}

function InboundScreen({ variant }: { variant: InboundVariant }) {
  return (
    <SceneShell route="/app/ff/reception">
      <FfInboundRequestView
        token={MOCK_TOKEN}
        requestId={INBOUND_IDS[variant]}
        isFulfillmentAdmin
        workspace="reception"
        onClose={() => {}}
      />
    </SceneShell>
  )
}

/** Колонка «ШК» листа приёмки в предложении: у микса оба кода, с пометкой площадки. */
function receivingSheetBarcode(product: DemoProduct): string | null {
  const wb = getDefaultCode(product, 'wb')
  const ozon = getDefaultCode(product, 'ozon')
  if (wb && ozon) return `WB ${wb} · Ozon ${ozon}`
  return wb ?? ozon
}

function PackagingScreen({ marketplace }: { marketplace: Marketplace }) {
  return (
    <SceneShell route={`/app/ff/packaging/${PACKAGING_IDS[marketplace]}`}>
      <Routes>
        <Route path="/app/ff/packaging" element={<FfPackagingPage token={MOCK_TOKEN} />} />
        <Route path="/app/ff/packaging/:taskId" element={<FfPackagingPage token={MOCK_TOKEN} />} />
      </Routes>
    </SceneShell>
  )
}

function FbsScreen({ marketplace, stage }: { marketplace: Marketplace; stage: FbsStage }) {
  return (
    <SceneShell route="/app/ff/fbs">
      <FfFbsSupplyWorkspace
        token={MOCK_TOKEN}
        authHeaders={authHeaders}
        supplyId={fbsSupplyId(marketplace, stage)}
        open
        onClose={() => {}}
      />
    </SceneShell>
  )
}

/**
 * «Честный знак»: настоящая страница пулов. Настоящая кнопка печати в строке открывает
 * окно без списка кодов площадок (опенер его не передаёт). В предложении тот же
 * клик ведёт в то же настоящее окно, но с тем списком, что передают каталог и приёмка.
 */
function HonestSignScreen({ mode }: { mode: MockMode }) {
  const { openPrint, dialog } = useMarkingCodePrint()
  const open = (productId: string) => {
    const product = productById(productId)
    if (!product) return
    const meta = catalogRowToDisplayMeta(catalogFields(product))
    openPrint({
      token: MOCK_TOKEN,
      source: 'catalog',
      productId: product.id,
      documentNumber: null,
      qtyNeedPack: 1,
      markingAvailable: 120,
      qtyMarkingPrinted: 0,
      requiresHonestSign: true,
      skuCode: product.sku,
      productName: product.name,
      productLabel: displayMetaToProductLabel(meta),
      productBarcodeOptions: meta.marketplace_bindings?.some((binding) => binding.marketplace === 'ozon')
        ? resolveProductBarcodeOptions(meta)
        : undefined,
      onPrinted: () => {},
    })
  }
  return (
    <InterceptClicks
      rules={
        mode === 'proposal'
          ? [
              {
                selector: '[data-testid*="-product-print-"]',
                handle: (element) => {
                  const testId = element.getAttribute('data-testid') ?? ''
                  open(testId.slice(testId.indexOf('-product-print-') + '-product-print-'.length))
                },
              },
            ]
          : []
      }
    >
      <SceneShell route="/app/ff/honest-sign">
        <FfHonestSignPage token={MOCK_TOKEN} sellers={[DEMO_SELLER]} />
      </SceneShell>
      {mode === 'proposal' ? dialog : null}
      {mode === 'proposal' ? <MarkingDialogOverlay docPlatform={null} /> : null}
    </InterceptClicks>
  )
}

/** Данные товара для настоящего окна ProductBarcodePrintDialog: первым идёт код нужной площадки. */
function labelMetaFor(product: DemoProduct, platform: Marketplace): ProductLineDisplayMeta {
  const meta = catalogRowToDisplayMeta(catalogFields(product))
  return platform === 'ozon'
    ? { ...meta, wb_primary_barcode: null, wb_barcodes: [] }
    : { ...meta, marketplace_bindings: [] }
}

/**
 * Кабинет селлера: черновик приёмки. Настоящая страница, настоящая кнопка печати
 * товарного ШК в строке. В «Сейчас» всё как в продукте: кнопка печатает только код WB
 * и погашена у товара «только Ozon». В предложении тот же клик открывает то же
 * настоящее окно с кодом нужной площадки; у «микса» в окне есть переключатель.
 */
function SellerDraftScreen({ mode }: { mode: MockMode }) {
  const [target, setTarget] = useState<DemoProduct | null>(null)
  const [platform, setPlatform] = useState<Marketplace>('wb')
  const rules =
    mode === 'proposal'
      ? [
          {
            selector: '[data-testid="seller-inbound-line-print-barcode"]',
            handle: (element: HTMLElement) => {
              const text = element.closest('tr')?.textContent ?? ''
              const product = PRODUCTS.find((item) => text.includes(item.sku))
              if (!product) return
              setPlatform(platformsOf(product)[0] ?? 'wb')
              setTarget(product)
            },
          },
        ]
      : []
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      {mode === 'proposal' ? (
        // Кнопка печати у товара «только Ozon» в настоящем экране погашена (у него
        // нет кода WB). В предложении она работает, поэтому макет рисует её как
        // обычную; клик перехватывает InterceptClicks (погашенная кнопка событий
        // не принимает, клик приходит на её обёртку).
        <style>{`
          [data-testid="seller-inbound-line-print-barcode"].Mui-disabled { color: rgba(0, 0, 0, 0.6) !important; opacity: 1 !important; }
          span:has(> [data-testid="seller-inbound-line-print-barcode"].Mui-disabled) { cursor: pointer; }
        `}</style>
      ) : null}
      <InterceptClicks rules={rules}>
        <>
          <MemoryRouter initialEntries={[`/app/seller/inbound/${INBOUND_IDS.seller}`]}>
            <AuthedAppLayout
              portal="seller"
              userLabel="seller@test-seller.ru"
              userRoleLabel="селлер"
              onLogout={() => {}}
            >
              <Box sx={{ minWidth: 0 }}>
                <Routes>
                  <Route
                    path="/app/seller/inbound/:requestId"
                    element={
                      <SellerInboundDraftScreen
                        token={MOCK_TOKEN}
                        authHeaders={authHeaders}
                        warehouseId={WAREHOUSE.id}
                        warehouses={[WAREHOUSE]}
                        onRefreshInboundList={() => {}}
                      />
                    }
                  />
                </Routes>
              </Box>
            </AuthedAppLayout>
          </MemoryRouter>
        </>
      </InterceptClicks>
      {mode === 'proposal' ? (
        <>
          <ProductBarcodePrintDialog
            open={target !== null}
            meta={target ? labelMetaFor(target, platform) : null}
            token={MOCK_TOKEN}
            productId={target?.id}
            onClose={() => setTarget(null)}
          />
          <ProductDialogOverlay product={target} platform={platform} onPlatform={setPlatform} />
        </>
      ) : null}
    </ThemeProvider>
  )
}

/** Колонка «ШК» листа упаковки отгрузки: ШК площадки документа. */
function packagingSheetBarcode(product: DemoProduct, marketplace: Marketplace): string | null {
  return getDefaultCode(product, marketplace)
}

export const FORMS: FormDef[] = [
  {
    id: 'card',
    title: 'Карточка товара · ШК по умолчанию',
    where: 'Каталог → клик по строке товара → карточка → вкладка «Основное»',
    platformKnown: 'нет',
    docToggle: false,
    hint: 'Кликните строку товара. В блоках «Wildberries» и «Ozon» у товара с несколькими кодами площадки появится выбор ШК по умолчанию.',
    routes: [],
    render: ({ mode }) => (
      <>
        <CatalogScreen />
        {mode === 'proposal' ? <ProductCardOverlay /> : null}
      </>
    ),
  },
  {
    id: 'catalog',
    title: 'Каталог · печать ШК товара',
    where: 'Каталог → значок принтера в строке товара',
    platformKnown: 'нет',
    docToggle: false,
    hint: 'Нажмите значок принтера в строке: у «микса» наверху окна печати выбор «Для WB | Для Ozon».',
    routes: [],
    render: ({ mode }) => (
      <>
        <CatalogScreen />
        {mode === 'proposal' ? <MarkingDialogOverlay docPlatform={null} /> : null}
      </>
    ),
  },
  {
    id: 'inbound',
    title: 'Приёмка · печать ШК в строке товара',
    where: 'Приёмка → документ → значок принтера у товара',
    platformKnown: 'нет',
    docToggle: false,
    hint: 'Нажмите значок принтера у строки товара в составе приёмки.',
    routes: inboundRoutes,
    render: ({ mode }) => (
      <>
        <InboundScreen variant="recv" />
        {mode === 'proposal' ? <MarkingDialogOverlay docPlatform={null} /> : null}
      </>
    ),
  },
  {
    id: 'inbound-sheet',
    title: 'Приёмка · лист приёмки («Печать накладной»)',
    where: 'Приёмка → документ → кнопка «Печать накладной»',
    platformKnown: 'нет',
    docToggle: false,
    hint: 'Нажмите «Печать накладной», затем «Журнал печати» → «Показать лист»: колонка ШК.',
    routes: inboundRoutes,
    render: ({ mode }) => (
      <InterceptClicks
        rules={
          mode === 'proposal'
            ? [
                {
                  selector: '[data-testid="ff-inbound-print-waybill"]',
                  handle: () =>
                    printInboundReceivingSheet({
                      documentNumber: '№000005',
                      sellerName: DEMO_SELLER.name,
                      warehouseName: `${WAREHOUSE.name} (${WAREHOUSE.code})`,
                      plannedDate: '2026-10-03',
                      items: receivingSheetItems(receivingSheetBarcode),
                    }),
                },
              ]
            : []
        }
      >
        <InboundScreen variant="recv" />
      </InterceptClicks>
    ),
  },
  {
    id: 'inbound-return',
    title: 'Приёмка-возврат · «Печатать ШК при скане»',
    where: 'Приёмка → возврат WB / Ozon → переключатель «Печатать ШК при скане» → скан товара',
    platformKnown: 'зависит от документа',
    docToggle: true,
    hint: 'Включите «Печатать ШК при скане» и введите ШК товара в строку скана (коды — в таблице).',
    scanCodes: (doc) =>
      inboundProducts(doc === 'ozon' ? 'ret-ozon' : 'ret-wb').flatMap((product) =>
        (doc === 'ozon' ? product.ozonCodes : product.wbCodes).map((code) => ({
          label: `${product.name} · ${code}`,
          code,
        })),
      ),
    routes: inboundRoutes,
    render: ({ doc }) => <InboundScreen variant={doc === 'ozon' ? 'ret-ozon' : 'ret-wb'} />,
  },
  {
    id: 'packaging',
    title: 'Упаковка отгрузки на МП · кнопка «ШК + ЧЗ»',
    where: 'Упаковка → задание по отгрузке на маркетплейс → кнопка печати у товара',
    platformKnown: 'зависит от документа',
    docToggle: true,
    hint: 'Нажмите «ШК + ЧЗ» / значок принтера у товара. Площадку даёт отгрузка, на которую ссылается задание.',
    routes: packagingRoutes,
    render: ({ mode, doc }) => (
      <>
        <PackagingScreen marketplace={doc} />
        {mode === 'proposal' ? <MarkingDialogOverlay docPlatform={doc} /> : null}
      </>
    ),
  },
  {
    id: 'packaging-sheet',
    title: 'Упаковка отгрузки на МП · лист отгрузки («Печать накладной»)',
    where: 'Упаковка → задание по отгрузке на маркетплейс → кнопка «Печать накладной»',
    platformKnown: 'зависит от документа',
    docToggle: true,
    hint: 'Нажмите «Печать накладной», затем «Журнал печати» → «Показать лист»: колонка ШК.',
    routes: packagingRoutes,
    render: ({ mode, doc }) => (
      <InterceptClicks
        rules={
          mode === 'proposal'
            ? [
                {
                  selector: '[data-testid="ff-packaging-print-sheet"]',
                  handle: () =>
                    printShipmentPackagingSheet({
                      documentNumber: doc === 'wb' ? '№000051' : '№000052',
                      documentType: 'Отгрузка на маркетплейс',
                      sellerName: DEMO_SELLER.name,
                      shipmentDate: null,
                      warehouseName: WAREHOUSE.name,
                      items: packagingProducts(doc).map((product) => ({
                        product_name: product.name,
                        vendor_code: product.vendorCode,
                        sku_code: product.sku,
                        barcode: packagingSheetBarcode(product, doc),
                        wb_nm_id: product.nmId,
                        photo_url: null,
                        instructions: product.packaging,
                        quantity: PACKAGING_QTY,
                      })),
                    }),
                },
              ]
            : []
        }
      >
        <PackagingScreen marketplace={doc} />
      </InterceptClicks>
    ),
  },
  {
    id: 'honest-sign',
    title: 'Честный знак · печать из пула кодов',
    where: 'Честный знак → значок принтера в строке товара',
    platformKnown: 'нет',
    docToggle: false,
    hint: 'Нажмите значок принтера в строке: сегодня окно открывается без выбора площадки.',
    routes: honestSignRoutes,
    render: ({ mode }) => <HonestSignScreen mode={mode} />,
  },
  {
    id: 'fbs-pack',
    title: 'FBS · упаковка: «Печать ЧЗ и ШК» / «Печать всего»',
    where: 'FBS → поставка → вкладка «Упаковка» → значок принтера у заказа или «Печать всего»',
    platformKnown: 'да',
    docToggle: true,
    hint: 'Нажмите значок принтера у заказа или «Печать всего». Площадку даёт поставка.',
    routes: fbsRoutes,
    render: ({ mode, doc }) => (
      <>
        <FbsScreen marketplace={doc} stage="packing" />
        {mode === 'proposal' ? <MarkingDialogOverlay docPlatform={doc} /> : null}
      </>
    ),
  },
  {
    id: 'fbs-pick-list',
    title: 'FBS · лист подбора',
    where: 'FBS → поставка → вкладка «Подбор» → «Печать листа подбора»',
    platformKnown: 'да',
    docToggle: true,
    hint: 'Нажмите «Печать листа подбора», затем «Журнал печати» → «Показать лист».',
    routes: fbsRoutes,
    render: ({ doc }) => <FbsScreen marketplace={doc} stage="picking" />,
  },
  {
    id: 'seller-draft',
    title: 'Кабинет селлера · печать товарного ШК в черновике приёмки',
    where: 'Портал селлера → Приёмка → черновик → значок принтера у товара',
    platformKnown: 'нет',
    docToggle: false,
    hint: 'Нажмите значок принтера у товара. Сегодня кнопка печатает только код WB и погашена у товара «только Ozon».',
    routes: inboundRoutes,
    render: ({ mode }) => <SellerDraftScreen mode={mode} />,
  },
]
