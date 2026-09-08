import { Autocomplete, createFilterOptions, Stack, TextField, Typography } from '@mui/material'
import { useState } from 'react'
import type { WbProductPickerCatalogRow } from '../../../components/WbProductPickerDialog'
import { AppDialog, PrimaryAction, SecondaryAction, SelectInput, TextInput } from '../../../ui-kit'

// Выбранные товары сужают существующий отбор. Пустой выбор берёт всё,
// что подходит под склад, селлера и категорию.
export type CreateFill = {
  seller: string | null
  category: string | null
  productIds: string[]
}

const filterProducts = createFilterOptions<WbProductPickerCatalogRow>({
  stringify: (product) => [
    product.name, product.sku_code, product.wb_vendor_code,
    product.wb_size, product.seller_name, ...product.wb_barcodes,
  ].filter(Boolean).join(' '),
})

type Props = {
  open: boolean
  warehouses: string[]
  sellers: string[]
  categories: string[]
  products?: WbProductPickerCatalogRow[] | null
  productsLoading?: boolean
  onClose: () => void
  onCreate: (warehouse: string, fill: CreateFill, comment: string) => void
}

export function InventoryCreateDialog({
  open,
  warehouses,
  sellers,
  categories,
  products = [],
  productsLoading = false,
  onClose,
  onCreate,
}: Props) {
  const [warehouse, setWarehouse] = useState(warehouses[0] ?? '')
  const [seller, setSeller] = useState('')
  const [category, setCategory] = useState('')
  const [comment, setComment] = useState('')
  const [selectedProducts, setSelectedProducts] = useState<WbProductPickerCatalogRow[]>([])

  const narrowed = Boolean(seller || category || selectedProducts.length)

  function submit() {
    onCreate(warehouse, {
      seller: seller || null,
      category: category || null,
      productIds: selectedProducts.map((product) => product.id),
    }, comment)
  }

  return (
    <AppDialog
      open={open}
      title="Новая инвентаризация"
      onClose={onClose}
      maxWidth="sm"
      testId="inventory-create-dialog"
      actions={
        <>
          <SecondaryAction onClick={onClose} data-testid="inv-create-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction onClick={submit} data-testid="inv-create-filters">
            Создать
          </PrimaryAction>
        </>
      }
    >
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          {narrowed
            ? 'В документ попадёт только то, что подходит под отбор.'
            : 'Фильтры не выбраны — в документ попадёт весь склад целиком.'}
        </Typography>
        <SelectInput
          label="Склад"
          value={warehouse}
          onChange={setWarehouse}
          options={warehouses.map((w) => ({ value: w, label: w }))}
          testId="inv-create-warehouse"
        />
        <SelectInput
          label="Селлер"
          value={seller}
          onChange={setSeller}
          options={sellers.map((s) => ({ value: s, label: s }))}
          emptyLabel="Все селлеры"
          testId="inv-create-seller"
        />
        <SelectInput
          label="Категория"
          value={category}
          onChange={setCategory}
          options={categories.map((c) => ({ value: c, label: c }))}
          emptyLabel="Все категории"
          testId="inv-create-category"
        />
        <Autocomplete
          multiple
          size="small"
          options={products ?? []}
          value={selectedProducts}
          onChange={(_, value) => setSelectedProducts(value)}
          loading={productsLoading}
          loadingText="Загрузка товаров…"
          noOptionsText={products === null ? 'Не удалось загрузить товары' : 'Товары не найдены'}
          disableCloseOnSelect
          filterSelectedOptions
          filterOptions={filterProducts}
          getOptionKey={(product) => product.id}
          isOptionEqualToValue={(option, value) => option.id === value.id}
          getOptionLabel={(product) => [
            product.name, product.sku_code, product.wb_size, product.seller_name,
          ].filter(Boolean).join(' · ')}
          data-testid="inv-create-products"
          renderInput={(params) => (
            <TextField
              {...params}
              label="Товары"
              placeholder={selectedProducts.length ? '' : 'Название, артикул или штрихкод'}
              helperText="Можно выбрать один или несколько. Пустой выбор — все товары по отбору."
            />
          )}
        />
        <TextInput
          label="Комментарий"
          value={comment}
          onChange={setComment}
          helperText="Зачем считаем. Виден в списке документов и в журнале движений."
          testId="inv-create-comment"
        />
      </Stack>
    </AppDialog>
  )
}
