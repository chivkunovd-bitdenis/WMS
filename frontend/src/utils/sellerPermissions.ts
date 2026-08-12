export type SellerPermissions = {
  documents: boolean
  products: boolean
  honest_sign: boolean
  settings: boolean
  staff: boolean
}

export const SELLER_PERMISSION_BLOCKS: {
  key: keyof SellerPermissions
  label: string
  hint: string
}[] = [
  {
    key: 'documents',
    label: 'Документы',
    hint: 'Заявки на поставку и отгрузки на маркетплейс',
  },
  {
    key: 'products',
    label: 'Товары',
    hint: 'Каталог и остатки селлера',
  },
  {
    key: 'honest_sign',
    label: 'Честный знак',
    hint: 'Коды маркировки и пул ЧЗ',
  },
  {
    key: 'settings',
    label: 'Настройки',
    hint: 'Интеграции WB и Честного Знака',
  },
  {
    key: 'staff',
    label: 'Сотрудники',
    hint: 'Создание сотрудников селлера и управление правами',
  },
]

export function emptySellerPermissions(): SellerPermissions {
  return {
    documents: false,
    products: false,
    honest_sign: false,
    settings: false,
    staff: false,
  }
}

export function resolveSellerPermissions(
  permissions: SellerPermissions | null | undefined,
): SellerPermissions {
  return permissions ?? emptySellerPermissions()
}

export function firstAllowedSellerPath(permissions: SellerPermissions): string {
  if (permissions.documents) return '/documents'
  if (permissions.products) return '/products'
  if (permissions.honest_sign) return '/honest-sign'
  if (permissions.settings || permissions.staff) return '/settings'
  return '/documents'
}
