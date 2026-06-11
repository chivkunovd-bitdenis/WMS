export type FfPermissions = {
  settings: boolean
  mp_shipments: boolean
  reception: boolean
  cells: boolean
  inventory: boolean
  packaging: boolean
}

export const FF_PERMISSION_BLOCKS: {
  key: keyof FfPermissions
  label: string
  hint: string
}[] = [
  {
    key: 'settings',
    label: 'Настройки',
    hint: 'Раздел настроек в меню',
  },
  {
    key: 'mp_shipments',
    label: 'Отгрузки на МП',
    hint: 'Просмотр и работа с отгрузками',
  },
  {
    key: 'reception',
    label: 'Приёмка',
    hint: 'Очередь приёмки и приём товара',
  },
  {
    key: 'cells',
    label: 'Ячейки',
    hint: 'Создание ячеек в каталоге',
  },
  {
    key: 'inventory',
    label: 'Инвентаризация',
    hint: 'Раздел инвентаризации (пока заглушка)',
  },
  {
    key: 'packaging',
    label: 'Упаковка',
    hint: 'Очередь и выполнение заданий на упаковку',
  },
]

export function adminFfPermissions(): FfPermissions {
  return {
    settings: true,
    mp_shipments: true,
    reception: true,
    cells: true,
    inventory: true,
    packaging: true,
  }
}

export function resolveFfPermissions(
  role: string,
  permissions: FfPermissions | null | undefined,
): FfPermissions {
  if (role === 'fulfillment_admin') {
    return adminFfPermissions()
  }
  return (
    permissions ?? {
      settings: false,
      mp_shipments: false,
      reception: false,
      cells: false,
      inventory: false,
      packaging: false,
    }
  )
}

export function canAccessFfBlock(
  role: string,
  permissions: FfPermissions | null | undefined,
  block: keyof FfPermissions,
): boolean {
  return resolveFfPermissions(role, permissions)[block]
}

export function isFfPortalRole(role: string): boolean {
  return role === 'fulfillment_admin' || role === 'fulfillment_staff'
}

export function isFulfillmentAdminRole(role: string): boolean {
  return role === 'fulfillment_admin'
}

export function ffRoleLabel(role: string): string {
  if (role === 'fulfillment_admin') {
    return 'администратор'
  }
  if (role === 'fulfillment_staff') {
    return 'сотрудник'
  }
  return role
}
