// Выдуманные данные макета: сервера нет, числа подобраны так, чтобы было видно
// все интересные случаи — смешанная ставка, услуга без тарифа, документ без
// товаров, хранение без документа.

export type RateKind = 'product' | 'seller' | 'common'

/** Одна применённая ставка — то, что раскрывается по значку в колонке «Ставка». */
export type AppliedRate = {
  kind: RateKind
  /** К чему применилась: название товара, имя селлера или «Общая ставка». */
  subject: string
  /** Копейки за единицу. */
  rateKopecks: number
  /** Сколько единиц посчитано по этой ставке. */
  quantity: number
}

export type DocumentRow = {
  id: string
  /** Номер документа. У хранения документа нет — там период. */
  number: string | null
  /** Подпись даты или периода. */
  date: string
  itemQuantity: number
  totalKopecks: number | null
  rates: AppliedRate[]
  /** Почему нет суммы, если её нет. */
  note?: string
}

export type ServiceRow = {
  id: string
  service: string
  documentCount: number
  itemQuantity: number
  totalKopecks: number | null
  rates: AppliedRate[]
  documents: DocumentRow[]
  note?: string
}

export type SellerRow = {
  id: string
  seller: string
  documentCount: number
  itemQuantity: number
  totalKopecks: number | null
  notBillable: number
  services: ServiceRow[]
}

const r = (kind: RateKind, subject: string, rateKopecks: number, quantity: number): AppliedRate => ({
  kind,
  subject,
  rateKopecks,
  quantity,
})

export const STUB_REPORT: SellerRow[] = [
  {
    id: 's1',
    seller: 'Denmarcs',
    documentCount: 14,
    itemQuantity: 1240,
    totalKopecks: 4_186_00,
    notBillable: 2,
    services: [
      {
        id: 's1-in',
        service: 'Приёмка',
        documentCount: 6,
        itemQuantity: 610,
        totalKopecks: 1_830_00,
        // Смешанный случай: два товара по своей цене, остальное по ставке селлера.
        rates: [
          r('product', 'FBS test product 1', 4_00, 120),
          r('product', 'FBS test product 3', 2_50, 90),
          r('seller', 'Denmarcs', 3_00, 400),
        ],
        documents: [
          {
            id: 'd1',
            number: 'ПРИЁМ-26-08-30-2',
            date: '30.08.2026, 11:54',
            itemQuantity: 110,
            totalKopecks: 330_00,
            rates: [r('seller', 'Denmarcs', 3_00, 110)],
          },
          {
            id: 'd2',
            number: 'ПРИЁМ-26-08-29-7',
            date: '29.08.2026, 09:12',
            itemQuantity: 210,
            totalKopecks: 705_00,
            rates: [
              r('product', 'FBS test product 1', 4_00, 120),
              r('seller', 'Denmarcs', 3_00, 90),
            ],
          },
          {
            id: 'd3',
            number: 'ПРИЁМ-26-08-27-1',
            date: '27.08.2026, 16:40',
            itemQuantity: 0,
            totalKopecks: null,
            rates: [],
            note: 'Документ без товаров',
          },
        ],
      },
      {
        id: 's1-out',
        service: 'Отгрузка',
        documentCount: 5,
        itemQuantity: 480,
        totalKopecks: 1_440_00,
        rates: [r('common', 'Общая ставка', 3_00, 480)],
        documents: [
          {
            id: 'd4',
            number: 'ОТГР-26-08-30-1',
            date: '30.08.2026, 10:05',
            itemQuantity: 300,
            totalKopecks: 900_00,
            rates: [r('common', 'Общая ставка', 3_00, 300)],
          },
          {
            id: 'd5',
            number: 'ОТГР-26-08-28-4',
            date: '28.08.2026, 18:22',
            itemQuantity: 180,
            totalKopecks: 540_00,
            rates: [r('common', 'Общая ставка', 3_00, 180)],
          },
        ],
      },
      {
        id: 's1-pack',
        service: 'Упаковка',
        documentCount: 3,
        itemQuantity: 150,
        totalKopecks: null,
        rates: [],
        note: 'Ставка не задана',
        documents: [
          {
            id: 'd6',
            number: 'УПАК-26-08-29-2',
            date: '29.08.2026, 14:30',
            itemQuantity: 150,
            totalKopecks: null,
            rates: [],
            note: 'Ставка не задана',
          },
        ],
      },
      {
        id: 's1-store',
        service: 'Хранение',
        documentCount: 0,
        itemQuantity: 0,
        totalKopecks: 916_00,
        rates: [r('seller', 'Denmarcs', 20, 45_800)],
        documents: [
          {
            id: 'd7',
            number: null,
            date: '01.08.2026 — 30.08.2026',
            itemQuantity: 0,
            totalKopecks: 916_00,
            rates: [r('seller', 'Denmarcs', 20, 45_800)],
            note: 'За период, литро-дни',
          },
        ],
      },
    ],
  },
  {
    id: 's2',
    seller: 'Северный ветер',
    documentCount: 3,
    itemQuantity: 96,
    totalKopecks: 288_00,
    notBillable: 0,
    services: [
      {
        id: 's2-in',
        service: 'Приёмка',
        documentCount: 3,
        itemQuantity: 96,
        totalKopecks: 288_00,
        rates: [r('common', 'Общая ставка', 3_00, 96)],
        documents: [
          {
            id: 'd8',
            number: 'ПРИЁМ-26-08-30-5',
            date: '30.08.2026, 12:41',
            itemQuantity: 96,
            totalKopecks: 288_00,
            rates: [r('common', 'Общая ставка', 3_00, 96)],
          },
        ],
      },
    ],
  },
  {
    id: 's3',
    seller: 'Луна Трейд',
    documentCount: 0,
    itemQuantity: 0,
    totalKopecks: null,
    notBillable: 0,
    services: [],
  },
]
