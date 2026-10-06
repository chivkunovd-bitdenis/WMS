export type FfPermissions = {
  settings: boolean
  mp_shipments: boolean
  reception: boolean
  cells: boolean
  inventory: boolean
  packaging: boolean
  shift_lead: boolean
}

export type FfStaffAccessKey =
  | 'reception'
  | 'shipments'
  | 'catalog_cells'
  | 'settings_staff'

export type FfStaffAccessState = Record<FfStaffAccessKey, boolean>

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
  {
    key: 'shift_lead',
    label: 'Старший смены',
    hint: 'Очередь перепечатки КМ и подтверждение брака',
  },
]

export const FF_STAFF_ACCESS_BLOCKS: {
  key: FfStaffAccessKey
  label: string
}[] = [
  { key: 'reception', label: 'Приёмка' },
  { key: 'shipments', label: 'Отгрузки' },
  { key: 'catalog_cells', label: 'Каталог и ячейки' },
  { key: 'settings_staff', label: 'Настройки и сотрудники' },
]

export function ffPermissionsToStaffAccess(
  permissions: FfPermissions,
): FfStaffAccessState {
  return {
    reception: permissions.reception,
    shipments: permissions.mp_shipments || permissions.packaging,
    catalog_cells: permissions.cells || permissions.inventory,
    settings_staff: permissions.settings,
  }
}

export function applyFfStaffAccessChange(
  permissions: FfPermissions,
  key: FfStaffAccessKey,
  checked: boolean,
): FfPermissions {
  if (key === 'reception') {
    return { ...permissions, reception: checked }
  }
  if (key === 'shipments') {
    return {
      ...permissions,
      mp_shipments: checked,
      packaging: checked,
      shift_lead: checked,
    }
  }
  if (key === 'catalog_cells') {
    return {
      ...permissions,
      cells: checked,
      inventory: checked,
    }
  }
  return { ...permissions, settings: checked }
}

export function adminFfPermissions(): FfPermissions {
  return {
    settings: true,
    mp_shipments: true,
    reception: true,
    cells: true,
    inventory: true,
    packaging: true,
    shift_lead: true,
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
      shift_lead: false,
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
