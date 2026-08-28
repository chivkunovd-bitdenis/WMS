import { Stack, Typography } from '@mui/material'
import { useState } from 'react'
import { AppDialog, PrimaryAction, SecondaryAction, SelectInput, TextInput } from '../../../ui-kit'

// Наполнение документа при создании. Владельцу нужны два способа: «взять всё»
// одной кнопкой и отбор по селлеру с категорией. Третьего пути — набирать строки
// руками — намеренно нет: инвентаризация начинается с того, что уже числится.

// Отдельной кнопки «весь склад» нет намеренно: не поставил фильтры — значит
// берём всё. Две кнопки для одного и того же заставляли выбирать там, где
// выбора нет.
export type CreateFill = { seller: string | null; category: string | null }

type Props = {
  open: boolean
  warehouses: string[]
  sellers: string[]
  categories: string[]
  onClose: () => void
  onCreate: (warehouse: string, fill: CreateFill, comment: string) => void
}

export function InventoryCreateDialog({
  open,
  warehouses,
  sellers,
  categories,
  onClose,
  onCreate,
}: Props) {
  const [warehouse, setWarehouse] = useState(warehouses[0] ?? '')
  const [seller, setSeller] = useState('')
  const [category, setCategory] = useState('')
  const [comment, setComment] = useState('')

  const narrowed = Boolean(seller || category)

  function submit() {
    onCreate(warehouse, { seller: seller || null, category: category || null }, comment)
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
