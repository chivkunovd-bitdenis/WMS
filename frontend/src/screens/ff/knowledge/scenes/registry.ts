import type { ComponentType, LazyExoticComponent } from 'react'
import { lazy } from 'react'

/**
 * Список живых макетов базы знаний.
 *
 * Каждый макет — настоящий экран портала на выдуманных данных. Из них
 * снимаются картинки для статей (страница `/kb-scenes.html?scene=<id>`), и их же
 * показывает проигрыватель сценария. Загружаются лениво: в обычной работе
 * портала макеты не нужны и не должны утяжелять первый экран.
 */

export type SceneId =
  | 'priemka-queue'
  | 'priemka-draft'
  | 'priemka-boxes'
  | 'priemka-box-fill'
  | 'priemka-done'
  | 'sorting-objects'
  | 'warehouse-map'
  | 'catalog'
  | 'catalog-create'
  | 'fbs-orders'
  | 'fbs-pick'
  | 'fbs-pack'
  | 'fbs-marking'
  | 'honest-sign'
  | 'honest-sign-print'
  | 'inventory-list'
  | 'inventory-count'
  | 'unload-pick'
  | 'billing'
  | 'billing-invoices'

export type SceneEntry = {
  id: SceneId
  /** Человеческое название — подпись в списке макетов. */
  title: string
  component: LazyExoticComponent<ComponentType>
}

export const SCENES: SceneEntry[] = [
  {
    id: 'priemka-queue',
    title: 'Приёмка · очередь документов',
    component: lazy(() => import('./PriemkaQueueScene')),
  },
  {
    id: 'priemka-draft',
    title: 'Приёмка · черновик с составом',
    component: lazy(() => import('./PriemkaDocScene').then((m) => ({ default: m.PriemkaDraftScene }))),
  },
  {
    id: 'priemka-boxes',
    title: 'Приёмка · короба и грузоместа',
    component: lazy(() => import('./PriemkaDocScene').then((m) => ({ default: m.PriemkaBoxesScene }))),
  },
  {
    id: 'priemka-box-fill',
    title: 'Приёмка · наполнение короба',
    component: lazy(() =>
      import('./PriemkaDocScene').then((m) => ({ default: m.PriemkaBoxFillScene })),
    ),
  },
  {
    id: 'priemka-done',
    title: 'Приёмка · сверка перед завершением',
    component: lazy(() => import('./PriemkaDocScene').then((m) => ({ default: m.PriemkaDoneScene }))),
  },
  {
    id: 'sorting-objects',
    title: 'Сортировка · раскладка по ячейкам',
    component: lazy(() => import('./WarehouseScenes').then((m) => ({ default: m.SortingScene }))),
  },
  {
    id: 'warehouse-map',
    title: 'Ячейки · карта склада',
    component: lazy(() => import('./WarehouseScenes').then((m) => ({ default: m.WarehouseMapScene }))),
  },
  {
    id: 'catalog',
    title: 'Каталог · список товаров',
    component: lazy(() => import('./CatalogScenes').then((m) => ({ default: m.CatalogScene }))),
  },
  {
    id: 'catalog-create',
    title: 'Каталог · карточка нового товара',
    component: lazy(() => import('./CatalogScenes').then((m) => ({ default: m.CatalogCreateScene }))),
  },
  {
    id: 'fbs-orders',
    title: 'FBS · заказы',
    component: lazy(() => import('./FbsScenes').then((m) => ({ default: m.FbsOrdersScene }))),
  },
  {
    id: 'fbs-pick',
    title: 'FBS · подбор',
    component: lazy(() => import('./FbsScenes').then((m) => ({ default: m.FbsPickScene }))),
  },
  {
    id: 'fbs-pack',
    title: 'FBS · упаковка и короба',
    component: lazy(() => import('./FbsScenes').then((m) => ({ default: m.FbsPackScene }))),
  },
  {
    id: 'fbs-marking',
    title: 'FBS · упаковка и маркировка',
    component: lazy(() => import('./FbsScenes').then((m) => ({ default: m.FbsMarkingScene }))),
  },
  {
    id: 'honest-sign',
    title: 'Честный знак · пулы кодов',
    component: lazy(() => import('./HonestSignScenes').then((m) => ({ default: m.HonestSignScene }))),
  },
  {
    id: 'honest-sign-print',
    title: 'Честный знак · окно печати',
    component: lazy(() =>
      import('./HonestSignScenes').then((m) => ({ default: m.HonestSignPrintScene })),
    ),
  },
  {
    id: 'inventory-list',
    title: 'Инвентаризация · документы пересчёта',
    component: lazy(() => import('./InventoryScenes').then((m) => ({ default: m.InventoryListScene }))),
  },
  {
    id: 'inventory-count',
    title: 'Инвентаризация · пересчёт',
    component: lazy(() =>
      import('./InventoryScenes').then((m) => ({ default: m.InventoryCountScene })),
    ),
  },
  {
    id: 'unload-pick',
    title: 'Отгрузка · подбор по ячейкам',
    component: lazy(() => import('./UnloadScenes').then((m) => ({ default: m.UnloadPickScene }))),
  },
  {
    id: 'billing',
    title: 'Расчёты · начисления за период',
    component: lazy(() => import('./BillingScenes').then((m) => ({ default: m.BillingScene }))),
  },
  {
    id: 'billing-invoices',
    title: 'Расчёты · тарифы селлера',
    component: lazy(() => import('./BillingScenes').then((m) => ({ default: m.BillingTariffScene }))),
  },
]

export function findScene(id: string | null): SceneEntry | undefined {
  return SCENES.find((scene) => scene.id === id)
}
