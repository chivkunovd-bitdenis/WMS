import type { ReactNode } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import type { ProductCardData } from './productCardTypes'

type Props = {
  data: ProductCardData
}

const EMPTY = '—'

function textOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY
  const text = String(value).trim()
  return text ? text : EMPTY
}

function barcodesOrDash(barcodes: string[]): string {
  const list = barcodes.map((b) => b.trim()).filter(Boolean)
  return list.length > 0 ? list.join(', ') : EMPTY
}

function dimensionsText(data: ProductCardData): string {
  if (data.length_mm == null && data.width_mm == null && data.height_mm == null) {
    return EMPTY
  }
  const part = (v: number | null) => (v == null ? EMPTY : String(v))
  return `${part(data.length_mm)} × ${part(data.width_mm)} × ${part(data.height_mm)} мм`
}

function weightText(data: ProductCardData): string {
  return data.weight_g == null ? EMPTY : `${data.weight_g} г`
}

// Пара «название — значение» в две колонки: подпись выравнивается по левому
// краю, значение занимает остаток строки и переносится, если не влезает
// (R15 — длинные названия, составы и SKU Ozon не должны обрезаться).
function FieldRow({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: 'break-word' }} data-testid={testId}>
        {value}
      </Typography>
    </>
  )
}

function FieldGrid({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'minmax(160px, max-content) 1fr',
        rowGap: 1,
        columnGap: 3,
      }}
    >
      {children}
    </Box>
  )
}

export function ProductCardMainTab({ data }: Props) {
  const hasWb = data.marketplaces.includes('wb')
  const hasOzon = data.marketplaces.includes('ozon')
  const ozonBinding = data.marketplace_bindings.find((b) => b.marketplace === 'ozon') ?? null

  return (
    <Stack spacing={3} data-testid="product-card-main-tab">
      <FieldGrid>
        <FieldRow label="Селлер" value={textOrDash(data.seller_name)} testId="product-card-field-seller" />
        <FieldRow label="Название" value={textOrDash(data.name)} testId="product-card-field-name" />
        <FieldRow label="SKU" value={textOrDash(data.sku_code)} testId="product-card-field-sku" />
        <FieldRow label="Размер" value={textOrDash(data.wb_size)} testId="product-card-field-size" />
        <FieldRow label="Цвет" value={textOrDash(data.wb_color)} testId="product-card-field-color" />
        <FieldRow label="Бренд" value={textOrDash(data.wb_brand)} testId="product-card-field-brand" />
        <FieldRow label="Состав" value={textOrDash(data.wb_composition)} testId="product-card-field-composition" />
        <FieldRow label="Категория" value={textOrDash(data.wb_subject_name)} testId="product-card-field-category" />
        <FieldRow
          label="Страна изготовления"
          value={textOrDash(data.country_of_origin_iso_code)}
          testId="product-card-field-country"
        />
        <FieldRow label="Габариты (Д × Ш × В, мм)" value={dimensionsText(data)} testId="product-card-field-dimensions" />
        <FieldRow label="Вес (г)" value={weightText(data)} testId="product-card-field-weight" />
        <FieldRow
          label="Честный знак"
          value={data.requires_honest_sign ? 'нужен' : 'не нужен'}
          testId="product-card-field-honest-sign"
        />
        <FieldRow
          label="Инструкция для склада"
          value={textOrDash(data.packaging_instructions)}
          testId="product-card-field-packaging"
        />
      </FieldGrid>

      {hasWb ? (
        <Stack spacing={1} data-testid="product-card-wb-section">
          <Typography variant="subtitle2">Wildberries</Typography>
          <FieldGrid>
            <FieldRow
              label="Артикул продавца"
              value={textOrDash(data.wb_vendor_code)}
              testId="product-card-wb-vendor-code"
            />
            <FieldRow label="Артикул WB" value={textOrDash(data.wb_nm_id)} testId="product-card-wb-nm-id" />
            <FieldRow label="ШК" value={barcodesOrDash(data.wb_barcodes)} testId="product-card-wb-barcodes" />
          </FieldGrid>
        </Stack>
      ) : null}

      {hasOzon ? (
        <Stack spacing={1} data-testid="product-card-ozon-section">
          <Typography variant="subtitle2">Ozon</Typography>
          <FieldGrid>
            <FieldRow
              label="Артикул"
              value={textOrDash(ozonBinding?.external_offer_id ?? data.ozon_offer_id)}
              testId="product-card-ozon-offer"
            />
            <FieldRow
              label="SKU"
              value={textOrDash(ozonBinding?.external_sku ?? data.ozon_sku)}
              testId="product-card-ozon-sku"
            />
            <FieldRow
              label="Product ID"
              value={textOrDash(ozonBinding?.external_product_id)}
              testId="product-card-ozon-product-id"
            />
            <FieldRow
              label="ШК"
              value={barcodesOrDash(ozonBinding?.external_barcodes ?? [])}
              testId="product-card-ozon-barcodes"
            />
          </FieldGrid>
        </Stack>
      ) : null}

      {!hasWb && !hasOzon && data.wb_barcodes.length > 0 ? (
        <FieldGrid>
          <FieldRow label="ШК" value={barcodesOrDash(data.wb_barcodes)} testId="product-card-barcodes-generic" />
        </FieldGrid>
      ) : null}
    </Stack>
  )
}
