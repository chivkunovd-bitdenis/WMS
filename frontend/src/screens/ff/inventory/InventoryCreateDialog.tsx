import { Stack, Typography } from '@mui/material'
import { useState } from 'react'
import { AppDialog, PrimaryAction, SecondaryAction, SelectInput, TextInput } from '../../../ui-kit'

// Наполнение документа при создании. Владельцу нужны два способа: «взять всё»
// одной кнопкой и отбор по селлеру с категорией. Третьего пути — набирать строки
// руками — намеренно нет: инвентаризация начинается с того, что уже числится.

export type CreateFill =
  | { mode: 'all' }
  | { mode: 'filters'; seller: string | null; category: string | null }

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

  function submit(mode: 'all' | 'filters') {
    onCreate(
      warehouse,
      mode === 'all'
        ? { mode: 'all' }
        : { mode: 'filters', seller: seller || null, category: category || null },
      comment,
    )
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
          <SecondaryAction onClick={() => submit('all')} data-testid="inv-create-all">
            Весь склад
          </SecondaryAction>
          <PrimaryAction
            onClick={() => submit('filters')}
            disabledReason={narrowed ? undefined : 'Выберите селлера или категорию'}
            data-testid="inv-create-filters"
          >
            Создать по отбору
          </PrimaryAction>
        </>
      }
    >
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          Документ наполняется тем, что числится на складе прямо сейчас. Можно взять склад
          целиком или сузить отбор — тогда в документ попадут только подходящие товары.
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
