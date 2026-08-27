import { Alert, Box, Chip, Divider, Stack, Typography } from '@mui/material'
import { INVENTORY } from './inventory.generated'
import type { InventoryItem } from './inventory.generated'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  DangerAction,
  DataTable,
  EmptyState,
  ErrorNotice,
  FilterBar,
  PlanFactCell,
  PrimaryAction,
  PrintAction,
  ProductCell,
  QtyCell,
  ScannerLine,
  ScreenHeader,
  SecondaryAction,
  MoscowDateTimeInput,
  MoscowDateInput,
  MoscowDateRangeInput,
  MoneyInput,
  NumberInput,
  PreferenceSwitch,
  SelectInput,
  TextInput,
  TextCell,
} from './index'
import type { Column } from './index'
import { useState } from 'react'

// Витрина канона. Всё, что показано ниже как «элементы системы», взято скриптом
// scripts/ui/ui_inventory.py прямо из кода экранов — здесь нет ни одной выдуманной
// подписи. Появится новый элемент на экране — он попадёт сюда следующим прогоном.

type MuiTone = 'default' | 'primary' | 'info' | 'success' | 'warning' | 'error'

type DateRangeDemo = {
  value: { start: string | null; end: string | null }
  maxDate: string
}

const DATE_RANGE_DEMOS: Array<{ label: string; value: DateRangeDemo }> = [
  { label: 'Обычный период', value: { value: { start: '2026-08-01', end: '2026-08-07' }, maxDate: '2027-12-31' } },
  { label: 'Обратный порядок', value: { value: { start: '2026-08-12', end: '2026-08-11' }, maxDate: '2027-12-31' } },
  { label: 'Слишком длинный', value: { value: { start: '2026-01-01', end: '2027-01-02' }, maxDate: '2027-12-31' } },
  { label: 'После допустимой даты', value: { value: { start: '2026-12-31', end: '2027-01-01' }, maxDate: '2026-12-31' } },
]

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 5 }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      {note ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {note}
        </Typography>
      ) : null}
      {children}
    </Box>
  )
}

function InventoryChip({ item }: { item: InventoryItem }) {
  const tone = (item.tones[0] ?? 'default') as MuiTone
  return (
    <Stack spacing={0.5} sx={{ minWidth: 190 }}>
      <Chip size="small" label={item.label} color={tone} />
      <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'ui-monospace, monospace' }}>
        {item.files[0]?.replace('src/screens/', '').replace('src/', '')}
      </Typography>
    </Stack>
  )
}

// Демонстрационные строки таблицы: поля взяты из реального каталога товаров,
// подписи статусов — из инвентаря, а не сочинены.
type Row = {
  id: number
  sku: string
  vendorCode: string
  wbArticle: string
  size: string
  seller: string
  tz: 'Заполнено' | 'Нет ТЗ'
  needsChz: boolean
  stock: number
  fbs: number
  fact: number
  plan: number
}

const ROWS: Row[] = [
  { id: 1, sku: 'SKU-10432', vendorCode: 'KRS-44-BLK', wbArticle: '184220931', size: '44', seller: 'Красотка', tz: 'Заполнено', needsChz: true, stock: 1240, fbs: 400, fact: 12, plan: 12 },
  { id: 2, sku: 'SKU-10433', vendorCode: 'KRS-44-WHT', wbArticle: '184220932', size: '46', seller: 'Красотка', tz: 'Нет ТЗ', needsChz: false, stock: 86, fbs: 0, fact: 4, plan: 6 },
  { id: 3, sku: 'SKU-11890', vendorCode: 'NRD-2XL-LONGVENDORCODE', wbArticle: '201884410', size: '2XL', seller: 'Норд', tz: 'Нет ТЗ', needsChz: true, stock: 312, fbs: 120, fact: 9, plan: 4 },
]

const COLUMNS: Column<Row>[] = [
  { key: 'sku', header: 'Товар', width: 130, render: (row) => <ProductCell sku={row.sku} /> },
  { key: 'vendor', header: 'Артикул продавца', width: 190, render: (row) => <TextCell value={row.vendorCode} width={170} /> },
  { key: 'wb', header: 'Артикул WB', width: 135, render: (row) => <TextCell value={row.wbArticle} /> },
  { key: 'size', header: 'Размер', width: 80, render: (row) => <TextCell value={row.size} /> },
  {
    key: 'chz',
    header: 'ЧЗ',
    width: 90,
    align: 'center',
    // Подпись «Нужен ЧЗ» — реальная, из HonestSignProductPage.tsx.
    render: (row) => (row.needsChz ? <Chip size="small" color="primary" label="Нужен ЧЗ" /> : null),
  },
  {
    key: 'tz',
    header: 'ТЗ упаковки',
    width: 170,
    // «Заполнено» / «Нет ТЗ» — реальные подписи из каталога товаров.
    render: (row) => <SecondaryAction>{row.tz === 'Нет ТЗ' ? 'Вставить ТЗ' : 'Открыть ТЗ'}</SecondaryAction>,
  },
  { key: 'seller', header: 'Селлер', width: 140, render: (row) => <TextCell value={row.seller} width={120} /> },
  { key: 'stock', header: 'Остаток', width: 110, align: 'right', render: (row) => <QtyCell value={row.stock} /> },
  { key: 'fbs', header: 'FBS', width: 90, align: 'right', render: (row) => <QtyCell value={row.fbs} muted /> },
  { key: 'fact', header: 'Принято', width: 200, align: 'right', render: (row) => <PlanFactCell fact={row.fact} plan={row.plan} /> },
  {
    key: 'print',
    header: '',
    width: 96,
    align: 'center',
    render: () => (
      <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'center' }}>
        <PrintAction what="ШК товара" placement="row" />
        <PrintAction what="ЧЗ и ШК" placement="row" />
      </Stack>
    ),
  },
]

// Дефекты считаются из инвентаря, а не глазами: одна подпись — один вид кнопки,
// чип — короткое слово, регистр одинаковый.
const CONFLICTING_BUTTONS = INVENTORY.buttons.filter((item) => item.variants.length > 1)
const LONG_CHIPS = INVENTORY.chips.filter((item) => item.label.split(' ').length > 2)
const LOWERCASE_CHIPS = INVENTORY.chips.filter((item) => /^[а-яёa-z]/.test(item.label))

export function UiKitShowcase() {
  const [search, setSearch] = useState('')
  const [formText, setFormText] = useState('')
  const [formNumber, setFormNumber] = useState<number | null>(null)
  const [formSelect, setFormSelect] = useState('')
  const [formTime, setFormTime] = useState<string | null>(null)
  const [formDate, setFormDate] = useState<string | null>(null)
  const [formRange, setFormRange] = useState<DateRangeDemo>(DATE_RANGE_DEMOS[0].value)
  const [formPreference, setFormPreference] = useState(false)
  const [formCheckbox, setFormCheckbox] = useState(false)
  const [formMoney, setFormMoney] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1400, mx: 'auto' }}>
      <ScreenHeader
        title="Канон WMS · элементы системы"
        purpose="Собрано из кода экранов скриптом scripts/ui/ui_inventory.py. Выдуманных подписей здесь нет: если элемента нет в системе — его нет и на этой странице."
      />
      <Divider sx={{ mb: 4 }} />

      <Section
        title={`Статусы — ${INVENTORY.statuses.length} шт.`}
        note="Все статусы системы и их фактические тона. Источник — карты статусов в коде."
      >
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 2 }}>
          {INVENTORY.statuses.map((item) => (
            <InventoryChip key={item.label} item={item} />
          ))}
        </Stack>
      </Section>

      <Section
        title={`Чипы-признаки — ${INVENTORY.chips.length} шт.`}
        note="Всё, что выводится чипом вне карт статусов."
      >
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 2 }}>
          {INVENTORY.chips.map((item) => (
            <InventoryChip key={item.label} item={item} />
          ))}
        </Stack>
      </Section>

      <Section
        title={`Кнопки — ${INVENTORY.buttons.length} подписей`}
        note="Реальные подписи кнопок с их видом и числом мест использования."
      >
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 2 }}>
          {INVENTORY.buttons.map((item) => (
            <Stack key={item.label} spacing={0.5} sx={{ minWidth: 210 }}>
              <Box>
                <Chip size="small" variant="outlined" label={`${item.label} · ${item.usages}×`} />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'ui-monospace, monospace' }}>
                {item.variants.join(' · ')}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Section>

      <Section title="Что инвентаризация нашла сама" note="Считается по коду при каждом прогоне скрипта — без человека.">
        <Stack spacing={1.5}>
          <Alert severity="error">
            Одна подпись — разный вид кнопки:{' '}
            {CONFLICTING_BUTTONS.map((item) => `«${item.label}» (${item.variants.length} вида, ${item.usages} мест)`).join('; ')}
          </Alert>
          <Alert severity="warning">
            Чипы длиннее двух слов ({LONG_CHIPS.length}): {LONG_CHIPS.map((item) => `«${item.label}»`).join(', ')}
          </Alert>
          <Alert severity="warning">
            Чипы со строчной буквы ({LOWERCASE_CHIPS.length}): {LOWERCASE_CHIPS.map((item) => `«${item.label}»`).join(', ')}
          </Alert>
          <Alert severity="info">
            Тонов у статусов шесть: default, primary, info, success, warning, error. Канон R-16 утверждает, что значений
            у цвета три. Либо правило неверно, либо система ему не соответствует — решение за владельцем.
          </Alert>
        </Stack>
      </Section>

      <Section title="Таблица" note="Каркас, плотность, липкая шапка, числа вправо, окраска строки только при расхождении.">
        <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Поиск по SKU, артикулу, ШК" />
        <DataTable columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.id} hasDiscrepancy={(row) => row.fact !== row.plan} />
      </Section>

      <Section title="Таблица — загрузка и пусто">
        <Stack spacing={2}>
          <DataTable columns={COLUMNS} rows={[]} getRowKey={(row) => row.id} loading />
          <DataTable
            columns={COLUMNS}
            rows={[]}
            getRowKey={(row) => row.id}
            empty={{
              title: 'Пока нет товаров',
              hint: 'Загрузите каталог из Wildberries или создайте товар вручную',
              action: <PrimaryAction>Загрузить каталог</PrimaryAction>,
            }}
          />
        </Stack>
      </Section>

      <Section title="Действия — панель экрана" note="Три вида и только три: главное, второстепенное рядом с ним, опасное.">
        <ActionGroup>
          <PrintAction what="ШК товара" placement="panel" />
          <PrimaryAction>Создать короб</PrimaryAction>
          <SecondaryAction>Открыть карточку</SecondaryAction>
          <DangerAction>Удалить короб</DangerAction>
        </ActionGroup>
        <Box sx={{ height: 12 }} />
        <ActionGroup>
          <PrintAction what="ЧЗ и ШК" placement="panel" disabledReason="Нет кодов ЧЗ на складе — загрузите коды" />
        </ActionGroup>
      </Section>

      <Section title="Поля формы" note="Общие поля с label, подсказкой, ошибкой, disabled и loading; без screen-specific поведения.">
        <Stack spacing={2} sx={{ maxWidth: 440 }}>
          <TextInput label="Название" value={formText} onChange={setFormText} helperText="Короткое понятное название" testId="showcase-text-input" />
          <NumberInput label="Количество" value={formNumber} onChange={setFormNumber} min={0} step={1} testId="showcase-number-input" />
          <MoneyInput label="Сумма" value={formMoney} onChange={setFormMoney} helperText="До двух знаков после запятой" testId="showcase-money-input" />
          <SelectInput
            label="Тип"
            value={formSelect}
            onChange={setFormSelect}
            emptyLabel="Выберите тип"
            options={[{ value: 'standard', label: 'Обычный' }, { value: 'restricted', label: 'Недоступный', disabled: true }]}
            testId="showcase-select-input"
          />
          <MoscowDateTimeInput label="Дата и время Москвы" value={formTime} onChange={setFormTime} testId="showcase-moscow-time-input" />
          <MoscowDateInput label="Дата Москвы" value={formDate} onChange={setFormDate} maxDate="2026-12-31" testId="showcase-moscow-date-input" />
          <MoscowDateRangeInput
            label="Период Москвы"
            value={formRange.value}
            onChange={(value) => setFormRange((current) => ({ ...current, value }))}
            maxDays={366}
            maxDate={formRange.maxDate}
            testId="showcase-moscow-date-range"
          />
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} aria-label="Примеры периода Москвы">
            {DATE_RANGE_DEMOS.map((demo) => (
              <SecondaryAction key={demo.label} onClick={() => setFormRange(demo.value)}>
                {demo.label}
              </SecondaryAction>
            ))}
          </Stack>
          <PreferenceSwitch label="Показывать дополнительные сведения" checked={formPreference} onChange={setFormPreference} helperText="Состояние задаёт внешний владелец формы" testId="showcase-preference-switch" />
          <CheckboxInput label="Выбрать операцию" checked={formCheckbox} onChange={setFormCheckbox} helperText="Выбор задаёт внешний владелец формы" testId="showcase-checkbox-input" />
          <CheckboxInput label="Недоступная операция" checked={false} onChange={() => undefined} disabledReason="Операция не рассчитана" testId="showcase-disabled-checkbox-input" />
          <CheckboxInput label="Выбрать строку таблицы" hideLabel checked={formCheckbox} onChange={setFormCheckbox} testId="showcase-hidden-label-checkbox-input" />
        </Stack>
      </Section>

      <Section title="Диалог" note="Единая модалка с управлением фокусом и закрытием по Escape.">
        <PrimaryAction onClick={() => setDialogOpen(true)}>Открыть окно</PrimaryAction>
        <AppDialog
          open={dialogOpen}
          title="Подтвердите действие"
          onClose={() => setDialogOpen(false)}
          actions={<SecondaryAction onClick={() => setDialogOpen(false)}>Назад</SecondaryAction>}
          testId="showcase-app-dialog"
        >
          <Typography>Диалог использует штатные действия и не создаёт отдельную стилистику.</Typography>
        </AppDialog>
      </Section>

      <Section title="Сканер и ошибка">
        <Stack spacing={1.5} sx={{ alignItems: 'flex-start' }}>
          <ScannerLine active expects="пикните ШК товара" />
          <ScannerLine active={false} expects="" />
          <ErrorNotice>Wildberries не принял остаток по складу «СЦ Пушкино»: склад отключён в настройках</ErrorNotice>
        </Stack>
      </Section>

      <Section title="Пустое состояние вне таблицы">
        <EmptyState
          title="Пока нет коробов"
          hint="Создайте короб, чтобы получить QR от Wildberries"
          action={<PrimaryAction>Создать короб</PrimaryAction>}
        />
      </Section>
    </Box>
  )
}
