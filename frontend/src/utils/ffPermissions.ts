export type FfPermissions = {
  settings: boolean
  mp_shipments: boolean
  reception: boolean
  cells: boolean
  inventory: boolean
  packaging: boolean
  shift_lead: boolean
  billing: boolean
  storage: boolean
  fbs: boolean
  honest_sign: boolean
}

export type FfStaffAccessKey = keyof FfPermissions

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
  { key: 'mp_shipments', label: 'Отгрузки' },
  { key: 'packaging', label: 'Упаковка' },
  { key: 'fbs', label: 'FBS' },
  { key: 'cells', label: 'Ячейки' },
  { key: 'storage', label: 'Хранение' },
  { key: 'inventory', label: 'Инвентаризация' },
  { key: 'billing', label: 'Расчёты' },
  { key: 'honest_sign', label: 'Честный знак' },
  { key: 'settings', label: 'Настройки' },
  { key: 'shift_lead', label: 'Старший смены' },
]

export function ffPermissionsToStaffAccess(
  permissions: FfPermissions,
): FfStaffAccessState {
  return permissions
}

export function applyFfStaffAccessChange(
  permissions: FfPermissions,
  key: FfStaffAccessKey,
  checked: boolean,
): FfPermissions {
  return { ...permissions, [key]: checked }
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
    billing: true,
    storage: true,
    fbs: true,
    honest_sign: true,
  }
}

export function resolveFfPermissions(
  role: string,
  permissions: FfPermissions | null | undefined,
): FfPermissions {
  if (role === 'fulfillment_admin') {
    return adminFfPermissions()
  }
  return {
    ...{
      settings: false,
      mp_shipments: false,
      reception: false,
      cells: false,
      inventory: false,
      packaging: false,
      shift_lead: false,
      billing: false,
      storage: false,
      fbs: false,
      honest_sign: false,
    },
    ...(permissions ?? {}),
  }
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
