export type FbsWarehouse = {
  id: string
  name: string
  code: string
  is_operational?: boolean
  is_primary?: boolean
}

export function operationalWarehouses<T extends FbsWarehouse>(rows: T[]): T[] {
  return rows.filter(
    (row) =>
      row.is_operational !== false &&
      !row.code.toLowerCase().startsWith('fbs-wb-') &&
      !row.name.toLowerCase().startsWith('fbs wb '),
  )
}

export function chooseWarehouseId(
  rows: FbsWarehouse[],
  previousId: string | null,
  storedId: string | null,
): string | null {
  if (rows.length === 0) return null
  if (previousId && rows.some((row) => row.id === previousId)) return previousId
  if (storedId && rows.some((row) => row.id === storedId)) return storedId
  return rows.find((row) => row.is_primary)?.id ?? rows[0]?.id ?? null
}
