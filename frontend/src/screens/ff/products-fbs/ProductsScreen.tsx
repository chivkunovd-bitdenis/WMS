import { Box, Stack, Typography } from '@mui/material'
import TuneOutlined from '@mui/icons-material/TuneOutlined'
import { useMemo, useState } from 'react'
import {
  CheckboxInput,
  DataTable,
  ErrorNotice,
  FilterBar,
  IconAction,
  PrimaryAction,
  QtyCell,
  ScreenHeader,
  SelectInput,
  StatusChip,
  TextCell,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { FbsStockDialog } from './FbsStockDialog'
import {
  INITIAL_RULES,
  PRODUCTS,
  SELLERS,
  freeStock,
  publishedQty,
  ruleFor,
  sellerById,
  type FbsRule,
  type Product,
} from './stub'

// Экран «Товары» — бывший «Каталог».
//
// Управление остатком для FBS переехало сюда с отдельной вкладки: настраивают
// его по товару, а не по складу, поэтому и жить оно должно там, где товар.
// Массовое присвоение — та же самая модалка, вызванная не с одной строки, а с
// нескольких: второго механизма для того же самого заводить незачем.

type Row = { product: Product; rule: FbsRule }

export function ProductsScreen({ onNote }: { onNote: (note: string) => void }) {
  const [rules, setRules] = useState<FbsRule[]>(INITIAL_RULES)
  const [query, setQuery] = useState('')
  const [sellerId, setSellerId] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<Product[] | null>(null)
  const [bulkError, setBulkError] = useState<string | null>(null)

  const rows: Row[] = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return PRODUCTS.filter((product) => {
      if (sellerId && product.sellerId !== sellerId) return false
      if (!needle) return true
      return [product.name, product.sku, product.barcode].some((value) =>
        value.toLowerCase().includes(needle),
      )
    }).map((product) => ({ product, rule: ruleFor(rules, product.id) }))
  }, [query, rules, sellerId])

  const chosen = PRODUCTS.filter((product) => selected.has(product.id))
  // Условие владельца: массово задавать процент можно только внутри одного
  // продавца. У разных продавцов разные склады, и «применить ко всем» тихо
  // разложило бы проценты не туда.
  const chosenSellers = new Set(chosen.map((one) => one.sellerId))

  function openBulk() {
    setBulkError(null)
    if (chosen.length === 0) return
    if (chosenSellers.size > 1) {
      setBulkError(
        'Выбраны товары разных продавцов. У каждого свои склады, поэтому один процент на всех задать нельзя — отфильтруйте по одному продавцу.',
      )
      return
    }
    setEditing(chosen)
  }

  const columns: Column<Row>[] = [
    {
      key: 'pick',
      header: '',
      width: 48,
      render: ({ product }) => (
        <CheckboxInput
          label={`Выбрать ${product.name}`}
          hideLabel
          checked={selected.has(product.id)}
          onChange={(checked) =>
            setSelected((current) => {
              const next = new Set(current)
              if (checked) next.add(product.id)
              else next.delete(product.id)
              return next
            })
          }
          testId={`products-pick-${product.id}`}
        />
      ),
    },
    {
      key: 'name',
      header: 'Товар',
      render: ({ product }) => (
        <Stack sx={{ minWidth: 0, py: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {product.name}
            {product.size ? `, ${product.size}` : ''}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {sellerById(product.sellerId).name} · {product.category}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'sku',
      header: 'Артикул',
      width: 132,
      render: ({ product }) => <TextCell value={product.sku} width={120} />,
    },
    {
      key: 'barcode',
      header: 'ШК',
      width: 134,
      render: ({ product }) => (
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: 12.5,
            color: 'text.secondary',
          }}
        >
          {product.barcode}
        </Typography>
      ),
    },
    {
      key: 'free',
      header: 'Свободно',
      width: 100,
      align: 'right',
      render: ({ product }) => <QtyCell value={freeStock(product)} />,
    },
    {
      key: 'fbs',
      header: 'В Wildberries',
      width: 190,
      render: ({ product, rule }) => {
        if (!rule.publish) {
          return (
            <Typography variant="body2" color="text.secondary">
              не передаётся
            </Typography>
          )
        }
        const qty = publishedQty(product, rule, sellerById(product.sellerId))
        return (
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <QtyCell value={qty} />
            <StatusChip
              label={rule.sameEverywhere ? `${rule.percent}%` : 'по складам'}
              tone="ok"
              hint="Доля свободного остатка — пересчитывается сама"
            />
          </Stack>
        )
      },
    },
    {
      key: 'actions',
      header: '',
      width: 56,
      align: 'right',
      render: ({ product }) => (
        <IconAction
          title="Настроить остаток для FBS"
          onClick={() => setEditing([product])}
          testId={`products-fbs-${product.id}`}
        >
          <TuneOutlined fontSize="small" />
        </IconAction>
      ),
    },
  ]

  return (
    <Box data-testid="products-screen">
      <ScreenHeader
        title="Товары"
        purpose="Каталог товаров фулфилмента и правила публикации остатка в маркетплейсы."
      />

      <FilterBar
        search={query}
        onSearchChange={setQuery}
        searchPlaceholder="Название, артикул или ШК"
        testId="products-filters"
        actions={
          <PrimaryAction
            onClick={openBulk}
            disabledReason={selected.size === 0 ? 'Отметьте товары галочками' : undefined}
            data-testid="products-bulk"
          >
            {`Задать остаток · ${selected.size}`}
          </PrimaryAction>
        }
      >
        <Box sx={{ minWidth: 220 }}>
          <SelectInput
            label="Продавец"
            value={sellerId}
            onChange={(value) => {
              setSellerId(value)
              setSelected(new Set())
              setBulkError(null)
            }}
            options={SELLERS.map((one) => ({ value: one.id, label: one.name }))}
            emptyLabel="Все продавцы"
            testId="products-filter-seller"
          />
        </Box>
      </FilterBar>

      {bulkError ? <ErrorNotice testId="products-bulk-error">{bulkError}</ErrorNotice> : null}

      <DataTable
        testId="products-table"
        columns={columns}
        rows={rows}
        getRowKey={({ product }) => product.id}
        empty={{ title: 'Ничего не нашлось', hint: 'Измените поиск или фильтр по продавцу.' }}
      />

      {editing ? (
        <FbsStockDialog
          open
          products={editing}
          seller={sellerById(editing[0]!.sellerId)}
          rule={ruleFor(rules, editing[0]!.id)}
          onClose={() => setEditing(null)}
          onSave={(rule) => {
            setRules((current) => {
              const ids = editing.map((one) => one.id)
              const rest = current.filter((one) => !ids.includes(one.productId))
              return [...rest, ...ids.map((productId) => ({ ...rule, productId }))]
            })
            onNote(
              editing.length > 1
                ? `Заглушка: правило применено к ${editing.length} товарам`
                : 'Заглушка: правило сохранено',
            )
            setEditing(null)
          }}
          onBind={(warehouseId, wbWarehouseId) =>
            onNote(`Заглушка: склад сопоставлен (${warehouseId} → ${wbWarehouseId || 'сброшено'})`)
          }
        />
      ) : null}
    </Box>
  )
}
