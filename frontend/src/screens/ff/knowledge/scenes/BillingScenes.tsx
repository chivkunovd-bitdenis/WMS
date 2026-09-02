import { useEffect, useLayoutEffect, useState } from 'react'
import { Stack } from '@mui/material'

import { ScreenHeader } from '../../../../ui-kit'
import { BillingReportScreen } from '../../billing-report/BillingReportScreen'
import { STUB_REPORT } from '../../billing-report/stub'
import { FfBillingTariffMatrixPanel } from '../../FfBillingTariffMatrixPanel'
import { SceneShell } from './SceneShell'
import { PRODUCTS, SELLERS } from './data'
import { installStubFetch } from './stubFetch'

/**
 * Деньги: что начислено за период и по каким ставкам это считается.
 *
 * Две разные истории, поэтому и сцены две. Отчёт по начислениям отвечает на
 * вопрос «сколько мы выставим селлеру», матрица тарифов — «откуда взялась эта
 * цифра». В портале они и живут в разных местах: отчёт в «Расчётах», тарифы —
 * в «Настройках», и подсветка меню в макетах это повторяет.
 */

/**
 * Отчёт по начислениям за период: селлер → услуга → документ.
 *
 * Данные — готовый `STUB_REPORT` из `billing-report/stub.ts`, тот же, что
 * показывает обычное превью `/raschety.html`. В нём нарочно собраны все
 * неудобные случаи: смешанная ставка, услуга без тарифа, документ без товаров
 * и хранение, у которого документа нет вовсе, — а есть период и литро-дни.
 *
 * Заголовок ставим сами: `BillingReportScreen` — это только таблица, шапку ей
 * даёт вызывающий экран. Без неё на картинке было бы непонятно, что за числа.
 */
export function BillingScene() {
  return (
    <SceneShell route="/app/ff/billing">
      <Stack spacing={2}>
        <ScreenHeader
          title="Расчёты"
          purpose="Начисления за период: селлер → услуга → документ. Раскройте строку, чтобы увидеть, из чего сложилась сумма."
        />
        <BillingReportScreen data={STUB_REPORT} />
      </Stack>
    </SceneShell>
  )
}

// ——— Тарифы ———

/**
 * Дата в прошлом или в будущем относительно «сейчас».
 *
 * Панель сама решает, какая версия ставки действует, сравнивая её дату с
 * текущим временем (`withRateState`). Прошей мы в макет календарные даты — и
 * через месяц-другой «запланированная» ставка молча стала бы действующей, а
 * ярлык «✓ Действует» переехал бы на другую строку. Картинка в инструкции
 * начала бы врать сама по себе, без единой правки кода.
 */
function shiftedByDays(days: number): string {
  const value = new Date(Date.now() + days * 24 * 60 * 60 * 1000)
  value.setUTCHours(9, 0, 0, 0)
  return value.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/** Селлер, чьи ставки раскрыты на картинке. */
const FOCUS_SELLER = SELLERS[1]

const EMPLOYEES = [
  { id: 'u-1', email: 'smirnova@korob-vms.ru', packaging_rate_rub: '12.00' },
  { id: 'u-2', email: 'kim@korob-vms.ru' },
]

/**
 * Ответ сервера на `GET /billing/tariff-matrix`.
 *
 * Ставки здесь в копейках — так их отдаёт настоящий бэкенд, а панель делит на
 * сто уже у себя (`matrixForDisplay`). Отдай мы рубли, 3,00 ₽ показались бы
 * как 0,03 ₽, и инструкция учила бы сотрудника читать неверные числа.
 */
function tariffMatrix() {
  const services = [
    { service_code: 'inbound', enabled: true, unit: 'item' as const, rate: 3_00, valid_from_at: shiftedByDays(-60) },
    { service_code: 'marketplace_outbound', enabled: true, unit: 'item' as const, rate: 3_00, valid_from_at: shiftedByDays(-60) },
    { service_code: 'picking', enabled: true, unit: 'item' as const, rate: 2_00, valid_from_at: shiftedByDays(-60) },
    { service_code: 'packing', enabled: true, unit: 'document' as const, rate: 45_00, valid_from_at: shiftedByDays(-30) },
    // Возврат заведён, но не тарифицируется: так видно оба состояния ярлыка.
    { service_code: 'return', enabled: false, unit: 'document' as const, rate: 0, valid_from_at: shiftedByDays(-60) },
    { service_code: 'storage', enabled: true, unit: 'item' as const, rate: 20, valid_from_at: shiftedByDays(-60) },
  ]

  const version = (
    seller_id: string | null,
    product_id: string | null,
    service_code: string,
    rate: number,
    valid_from_at: string,
    employee_user_id: string | null = null,
  ) => ({
    seller_id,
    product_id,
    employee_user_id,
    service_code,
    unit: 'item' as const,
    enabled: true,
    rate,
    valid_from_at,
    valid_to_at: null,
  })

  return {
    revision: 7,
    services,
    // Общие ставки тоже версии: панель показывает их в верхней таблице.
    versions: [
      ...services.map((service) =>
        version(null, null, service.service_code, service.rate, service.valid_from_at),
      ),
      // Своя ставка селлера на приёмку: старая версия перебита новой.
      version(FOCUS_SELLER.id, null, 'inbound', 2_50, shiftedByDays(-90)),
      version(FOCUS_SELLER.id, null, 'inbound', 2_80, shiftedByDays(-14)),
      version(FOCUS_SELLER.id, null, 'marketplace_outbound', 3_20, shiftedByDays(-14)),
      // Цена на конкретный товар перебивает ставку селлера.
      version(FOCUS_SELLER.id, 'p-3', 'inbound', 4_50, shiftedByDays(-7)),
      // Версия с будущей датой: ещё не вступила в силу, ярлыка «Действует» нет.
      version(FOCUS_SELLER.id, 'p-1', 'inbound', 5_00, shiftedByDays(21)),
      // Сдельные ставки сотрудников — нижняя таблица панели.
      version(null, null, 'inbound', 1_20, shiftedByDays(-30), 'u-1'),
      version(null, null, 'picking', 90, shiftedByDays(-30), 'u-1'),
      version(null, null, 'inbound', 1_10, shiftedByDays(-30), 'u-2'),
    ],
    products: PRODUCTS.map((product) => ({
      id: product.id,
      seller_id: SELLERS.find((seller) => seller.name === product.seller)?.id ?? null,
      name: product.name,
      sku: product.sku,
      seller_name: product.seller,
      label: `${product.sku} · ${product.name}`,
    })),
    sellers: SELLERS.map((seller) => ({ id: seller.id, name: seller.name })),
    storage: { mode: 'liter_day', editable_in_matrix: false },
  }
}

/**
 * Тарифы: общие ставки, ставки селлеров и сдельные ставки сотрудников.
 *
 * Это единственный экран в наборе, у которого своего стаба нет: панель не
 * принимает данные пропсами, она сама ходит на `GET /billing/tariff-matrix`.
 * Поэтому здесь подменяем `fetch` — и обязательно до первого рендера, иначе
 * панель успеет сходить на настоящий адрес, получить отказ и нарисовать
 * красную полосу ошибки, которая и попадёт на картинку.
 */
export function BillingTariffScene() {
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    const restore = installStubFetch([
      { method: '*', path: /^\/billing\/tariff-matrix$/, handler: () => tariffMatrix() },
    ])
    setReady(true)
    return restore
  }, [])

  /**
   * Раскрываем ставки одного селлера.
   *
   * Статья рассказывает именно про них, а панель по умолчанию держит всех
   * селлеров свёрнутыми, и раскрывашка — её внутреннее состояние, снаружи
   * пропом не задаётся. Поэтому нажимаем ту же кнопку, что нажал бы человек:
   * ждём, пока матрица доедет и строка селлера появится в разметке. Повторно
   * не нажимаем — проверяем, не раскрыт ли он уже, иначе второй заход свернул
   * бы всё обратно.
   */
  useEffect(() => {
    if (!ready) return
    const expandedId = `ff-settings-tariff-sellers-expanded-${FOCUS_SELLER.id}`
    const buttonId = `ff-settings-tariff-sellers-expand-${FOCUS_SELLER.id}`
    const timer = window.setInterval(() => {
      if (document.querySelector(`[data-testid="${expandedId}"]`)) {
        window.clearInterval(timer)
        return
      }
      const button = document.querySelector<HTMLElement>(`[data-testid="${buttonId}"]`)
      if (button) button.click()
    }, 120)
    // Сдаёмся через несколько секунд: если панель так и не приехала, вечный
    // таймер в макете хуже, чем свёрнутый список.
    const stop = window.setTimeout(() => window.clearInterval(timer), 5000)
    return () => {
      window.clearInterval(timer)
      window.clearTimeout(stop)
    }
  }, [ready])

  if (!ready) return null

  return (
    <SceneShell route="/app/ff/settings">
      <FfBillingTariffMatrixPanel
        token="kb-scene"
        authHeaders={() => ({})}
        focusTariffs={false}
        onSaved={() => {}}
        employees={EMPLOYEES}
      />
    </SceneShell>
  )
}
