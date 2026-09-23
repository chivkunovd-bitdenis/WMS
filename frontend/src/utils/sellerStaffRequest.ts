import { readApiErrorMessage } from './readApiErrorMessage'

export type SellerStaffAction = 'load' | 'create' | 'invite' | 'profile' | 'permissions'

const fallback: Record<SellerStaffAction, string> = {
  load: 'Не удалось загрузить сотрудников. Обновите страницу и попробуйте ещё раз.',
  create: 'Не удалось добавить сотрудника. Обновите список и попробуйте ещё раз.',
  invite: 'Не удалось отправить приглашение. Попробуйте ещё раз.',
  profile: 'Не удалось сохранить данные сотрудника. Попробуйте ещё раз.',
  permissions: 'Не удалось сохранить права сотрудника. Попробуйте ещё раз.',
}

const known: Record<string, string> = {
  email_taken: 'Этот email уже используется',
  forbidden: 'Нет доступа к сотрудникам',
  seller_not_linked: 'Нет доступа к сотрудникам',
  not_seller_user: 'Сотрудник не найден',
  user_not_found: 'Сотрудник не найден',
  owner_protected: 'Нельзя снять последний полный доступ к кабинету',
  self_update_forbidden: 'Нельзя изменить собственный доступ',
  email_already_set: 'Email уже задан. Обновите список сотрудников.',
  account_already_active: 'Сотрудник уже активировал доступ. Для восстановления пароля используйте «Забыли пароль» при входе.',
  email_required: 'Сначала добавьте email сотрудника.',
}

class SellerStaffRequestError extends Error {}

export function sellerStaffError(error: unknown, action: SellerStaffAction): string {
  return error instanceof SellerStaffRequestError ? error.message : fallback[action]
}

/** Only our translated errors reach the screen; transport/server text stays private. */
export async function sellerStaffRequest(
  url: string, init: RequestInit, action: SellerStaffAction,
): Promise<Response> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new SellerStaffRequestError(fallback[action])
  }
  if (!response.ok) {
    const detail = await readApiErrorMessage(response)
    throw new SellerStaffRequestError(known[detail] ?? fallback[action])
  }
  return response
}
