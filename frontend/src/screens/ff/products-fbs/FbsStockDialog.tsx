import { ErrorBoundary } from '../../../components/errors/ErrorBoundary'
import {
  Box,
  FormControlLabel,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  Slider,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import CloseIcon from '@mui/icons-material/Close'
import { useEffect, useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  ErrorNotice,
  MARKETPLACE_LABELS,
  MARKETPLACE_PALETTE,
  MarketplaceIcon,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  StatusChip,
} from '../../../ui-kit'
import {
  WAREHOUSE_NAME_ISSUE_LABELS,
  warehouseNameIssueHint,
  type CabinetList,
} from './fbsSellerWarehouseRows'
import {
  addableWarehouses,
  blockTotals,
  capNoteText,
  clampUnits,
  draftFromState,
  NUMBER_FORMAT,
  PERCENT_STEP,
  pluralRu,
  rowCalc,
  ruleBodyFromDrafts,
  snapPercent,
  toggleByPercent,
  unitsCap,
  visibleStockBindings,
  type BlockDraft,
  type CabinetWarehouse,
  type StockBinding,
  type StockDialogProduct,
} from './fbsStockBlocks'
import type { MarketplaceCode } from './stub'

// Окно «Остаток для FBS» по принятому макету WMS-469.
//
// Блок = один склад продавца из кабинета площадки ↔ склад ФФ. Внутри блока —
// галка приёма заказов (свойство продавца, сохраняется сразу) и одна строка
// площадки этой привязки: переключатель передачи, ползунок в цвете площадки,
// поле «шт» и галочка «процентом». Процент и число — два представления одного
// лимита, расходиться они не могут. Лимиты выбранных товаров сохраняются
// кнопкой «Сохранить»; связка и приём заказов — в момент действия.

export type FbsStockDialogProps = {
  open: boolean
  sellerName: string
  /** Один товар или несколько — окно одно и то же. */
  products: StockDialogProduct[]
  /** Активные привязки продавца с названиями из кабинетов. */
  bindings: StockBinding[]
  /** Ответы кабинетов — из них строится список «Добавить склад». */
  cabinets: Record<MarketplaceCode, CabinetList>
  /** Физические склады ФФ для выбора в шапке блока и при добавлении. */
  wmsWarehouses: Array<{ id: string; name: string }>
  /**
   * Можно ли из этого кабинета добавлять связки, менять склад ФФ и приём
   * заказов. У селлера — нет (D4): контролы видны, но только читаются.
   */
  canEditBindings: boolean
  /** Идёт запрос: кнопки действий заперты, чтобы не отправить дважды. */
  busy?: boolean
  onClose: () => void
  /** Сохранить правило выбранных товаров по привязкам. */
  onSave: (byBinding: Record<string, {
    publish: boolean
    mode: 'percent' | 'units'
    value: number
    units_configured: boolean
  }>) => void
  /** Добавить связку «склад продавца ↔ склад ФФ». Сохраняется сразу. */
  onAddBinding?: (warehouse: CabinetWarehouse, wmsWarehouseId: string) => void
  /** Сменить склад ФФ у готовой связки. Сохраняется сразу. */
  onChangeWmsWarehouse?: (binding: StockBinding, wmsWarehouseId: string) => void
  /** Принимаем ли заказы со склада продавца. Свойство продавца, сохраняется сразу. */
  onServedChange?: (binding: StockBinding, served: boolean) => void
  /** Отказ сервера или потеря ответа. Показываем здесь: окно с введённым не закрываем. */
  actionError?: string | null
  /** Почему кабинет Wildberries не отдал список складов — плашка сверху окна. */
  wbWarehousesError?: string | null
  /** Почему не приехал справочник складов Ozon. */
  ozonWarehousesError?: string | null
  /**
   * Сервер сохранил отправленные блоки, но часть — меньше запрошенного:
   * свободный остаток изменился между открытием и сохранением. Черновики
   * обрезанных блоков принимают сохранённое, подпись называет ограничивший
   * товар; отметки «изменён» снимаются только с блоков, которые были в
   * запросе.
   */
  saved?: SavedRule
}

export type SavedRule = {
  /** Блоки, которые были в запросе и сохранены. */
  bindingIds: string[]
  /** Обрезка по блокам: сохранённое число и ограничивший товар. */
  clamps: Record<string, { free: number; product: { name: string } }>
}

export function FbsStockDialog(props: FbsStockDialogProps) {
  if (!props.open) return null
  return (
    <ErrorBoundary component="FbsStockDialog" resetKey={String(props.open)}>
      <FbsStockDialogBody {...props} />
    </ErrorBoundary>
  )
}

type Picker = { warehouse: CabinetWarehouse | null; wmsWarehouseId: string | null }

function FbsStockDialogBody({
  sellerName,
  products,
  bindings,
  cabinets,
  wmsWarehouses,
  canEditBindings: canEditFromCabinet,
  busy = false,
  onClose,
  onSave,
  onAddBinding,
  onChangeWmsWarehouse,
  onServedChange,
  actionError,
  wbWarehousesError,
  ozonWarehousesError,
  saved,
}: FbsStockDialogProps) {
  const many = products.length > 1
  const first = products[0]!
  const visible = visibleStockBindings(bindings, products)
  // Право на связки решают кабинет и ответ сервера вместе: у селлера привязки
  // приходят с editable=false, и PUT от его имени сервер всё равно отклонит.
  const canEditBindings = canEditFromCabinet && bindings.every((one) => one.editable)

  // Черновики по id привязки. Тело монтируется на каждое открытие, а связки
  // могут появляться прямо в окне: черновик новой привязки берётся из
  // сохранённого состояния первого товара в момент, когда она впервые видна.
  const [drafts, setDrafts] = useState<Record<string, BlockDraft>>({})
  // Блоки, которые оператор менял в этом открытии. Сохраняются только они:
  // нетронутый блок соседней площадки у остальных выбранных товаров остаётся
  // со своим правилом (R8, R24), а пустой набор изменений не отправляется.
  const [touched, setTouched] = useState<Set<string>>(() => new Set())
  const [capNotes, setCapNotes] = useState<Record<string, { free: number; product: { name: string } }>>({})
  const [picker, setPicker] = useState<Picker | null>(null)
  // Смена склада ФФ, которую оператор только что запросил: после того как
  // перечитанная связка действительно встала на новый склад, ручное число
  // сверяется с остатком уже там. Отказ смены ничего не трогает.
  const [reclamp, setReclamp] = useState<{ bindingId: string; wmsWarehouseId: string } | null>(null)
  const draftOf = (binding: StockBinding): BlockDraft =>
    drafts[binding.id] ?? draftFromState(first.byBinding[binding.id])
  const patchDraft = (binding: StockBinding, next: BlockDraft) => {
    setDrafts((current) => ({ ...current, [binding.id]: next }))
    setTouched((current) => (current.has(binding.id) ? current : new Set(current).add(binding.id)))
  }
  const setNote = (bindingId: string, note: { free: number; product: { name: string } } | null) =>
    setCapNotes((current) => {
      if (!note && !(bindingId in current)) return current
      const next = { ...current }
      if (note) next[bindingId] = note
      else delete next[bindingId]
      return next
    })

  // Сохранённый операторский потолок при открытии и перечитывании не трогаем,
  // даже если он выше текущего свободного остатка: лимит меняет только
  // оператор, а уедет всё равно min(лимит, свободно) (R14). Обрезка — только
  // для нового ввода (в поле) и после явной смены склада ФФ, когда остаток
  // считается уже по другому складу (R6, R12). Основание — перечитанные
  // связки: пока связка не встала на запрошенный склад (ответа ещё нет либо
  // сервер отказал), число и подпись остаются прежними. Блок с выключенной
  // передачей не трогаем.
  useEffect(() => {
    if (!reclamp) return
    const binding = bindings.find((one) => one.id === reclamp.bindingId)
    if (!binding) return
    if (binding.wmsWarehouseId !== reclamp.wmsWarehouseId) return
    setReclamp(null)
    const draft = draftOf(binding)
    const cap = unitsCap(binding, products)
    if (draft.publish && !draft.byPercent && draft.units !== null && draft.units > cap.free) {
      patchDraft(binding, { ...draft, units: cap.free })
      setNote(binding.id, cap)
    } else {
      // Подпись про прежний склад больше не про этот блок.
      setNote(binding.id, null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bindings])

  // Запись завершилась, а связка на запрошенный склад не встала (отказ, в том
  // числе без перечитывания): ожидание снимается, чтобы не сработать на
  // каком-нибудь позднем перечитывании.
  useEffect(() => {
    if (busy || !reclamp) return
    const binding = bindings.find((one) => one.id === reclamp.bindingId)
    if (!binding || binding.wmsWarehouseId !== reclamp.wmsWarehouseId) setReclamp(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy])

  // Сервер сохранил отправленные блоки: их отметки «изменён» снимаются, а
  // черновики обрезанных блоков принимают сохранённое с подписью, которая
  // снимется новым вводом, как местная (R12). Черновик блока, не входившего
  // в запрос (например, со снятым приёмом заказов), остаётся изменённым и
  // уйдёт при следующем сохранении.
  useEffect(() => {
    if (!saved) return
    setTouched((current) => {
      const next = new Set(current)
      for (const bindingId of saved.bindingIds) next.delete(bindingId)
      return next
    })
    for (const [bindingId, clamp] of Object.entries(saved.clamps)) {
      setDrafts((current) => {
        const base = current[bindingId] ?? draftFromState(first.byBinding[bindingId])
        return { ...current, [bindingId]: { ...base, byPercent: false, units: clamp.free } }
      })
      setNote(bindingId, clamp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saved])

  const addable = addableWarehouses(cabinets, bindings)
  const anyCabinetReceived = cabinets.wb.received || cabinets.ozon.received
  const addDisabledReason = !anyCabinetReceived
    ? 'Список складов из кабинета не получен — добавить склад пока нельзя'
    : addable.length === 0
      ? 'Все склады селлера уже добавлены'
      : undefined

  function openPicker() {
    // Единственный склад ФФ подставляется сам; при нескольких выбирают явно.
    setPicker({
      warehouse: null,
      wmsWarehouseId: wmsWarehouses.length === 1 ? wmsWarehouses[0]!.id : null,
    })
  }

  function pickerChange(next: Picker) {
    // Пока идёт запись, форма заперта: второй запрос поверх первого не начинаем.
    if (busy) return
    if (next.warehouse && next.wmsWarehouseId) {
      // Связка — свойство продавца: запоминается сразу после выбора пары.
      onAddBinding?.(next.warehouse, next.wmsWarehouseId)
      setPicker(null)
      return
    }
    setPicker(next)
  }

  const productsWord = pluralRu(products.length, 'товар', 'товара', 'товаров')

  return (
    <AppDialog
      open
      // Пока идёт запись, Escape и клик по фону окно не закрывают: ответ
      // должен подтвердить именно тот черновик, который отправлен.
      onClose={busy ? () => undefined : onClose}
      maxWidth="md"
      testId="fbs-stock-dialog"
      title={many ? `Остаток для FBS · ${products.length} ${productsWord}` : 'Остаток для FBS'}
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="fbs-stock-cancel" disabled={busy}>
            Отмена
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onSave(ruleBodyFromDrafts(
              visible.filter((binding) => touched.has(binding.id)),
              Object.fromEntries(visible.map((binding) => [binding.id, draftOf(binding)])),
            ))}
            data-testid="fbs-stock-save"
            disabled={busy}
          >
            Сохранить
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2.5}>
        {/* Отказ сервера показываем здесь, а не наверху страницы: оператор
            смотрит в это окно и должен видеть, что именно не сошлось, не теряя
            уже введённого. */}
        {wbWarehousesError ? (
          <ErrorNotice testId="fbs-stock-wb-directory-error">{wbWarehousesError}</ErrorNotice>
        ) : null}
        {/* Причина, почему у сохранённого Ozon-блока номер вместо названия, —
            здесь же, в окне: у селлера формы добавления нет, а чип без
            причины ничего не объясняет (R19). */}
        {ozonWarehousesError && visible.some((one) => one.marketplace === 'ozon' && one.nameIssue === 'list_unavailable') ? (
          <ErrorNotice testId="fbs-stock-ozon-directory-error">{ozonWarehousesError}</ErrorNotice>
        ) : null}
        {actionError ? <ErrorNotice testId="fbs-stock-error">{actionError}</ErrorNotice> : null}

        <Typography variant="subtitle2" sx={{ overflowWrap: 'anywhere' }} data-testid="fbs-stock-head">
          {many
            ? `${products.length} ${productsWord}, ${sellerName}`
            : `${first.name}${first.size ? `, ${first.size}` : ''} · ${first.sku}`}
        </Typography>

        {visible.map((binding) => (
          <BindingBlock
            key={binding.id}
            binding={binding}
            products={products}
            draft={draftOf(binding)}
            capNote={capNotes[binding.id]}
            wmsWarehouses={wmsWarehouses}
            editable={canEditBindings && binding.editable}
            busy={busy}
            onDraft={(next) => patchDraft(binding, next)}
            onCapNote={(note) => setNote(binding.id, note)}
            onChangeWmsWarehouse={(id) => {
              setReclamp({ bindingId: binding.id, wmsWarehouseId: id })
              onChangeWmsWarehouse?.(binding, id)
            }}
            onServedChange={(served) => onServedChange?.(binding, served)}
          />
        ))}

        {visible.length === 0 && !picker ? (
          <Typography color="text.secondary" data-testid="fbs-stock-empty">
            Склады селлера ещё не добавлены.
          </Typography>
        ) : null}

        {picker ? (
          <BindingPicker
            picker={picker}
            addable={addable}
            wmsWarehouses={wmsWarehouses}
            ozonWarehousesError={cabinets.ozon.received ? null : (ozonWarehousesError ?? null)}
            busy={busy}
            onChange={pickerChange}
            onCancel={() => setPicker(null)}
          />
        ) : canEditBindings && onAddBinding ? (
          <Box>
            <Tooltip title={addDisabledReason ?? ''}>
              <span style={{ display: 'inline-flex' }}>
                <SecondaryAction
                  onClick={openPicker}
                  disabled={Boolean(addDisabledReason) || busy}
                  startIcon={<AddIcon />}
                  data-testid="fbs-stock-add"
                >
                  Добавить склад
                </SecondaryAction>
              </span>
            </Tooltip>
          </Box>
        ) : null}
      </Stack>
    </AppDialog>
  )
}

function BindingBlock({
  binding,
  products,
  draft,
  capNote,
  wmsWarehouses,
  editable,
  busy,
  onDraft,
  onCapNote,
  onChangeWmsWarehouse,
  onServedChange,
}: {
  binding: StockBinding
  products: StockDialogProduct[]
  draft: BlockDraft
  capNote?: { free: number; product: { name: string } }
  wmsWarehouses: Array<{ id: string; name: string }>
  editable: boolean
  busy: boolean
  onDraft: (next: BlockDraft) => void
  onCapNote: (note: { free: number; product: { name: string } } | null) => void
  onChangeWmsWarehouse: (wmsWarehouseId: string) => void
  onServedChange: (served: boolean) => void
}) {
  const totals = blockTotals(binding, products)
  const calc = rowCalc(binding, draft, products)
  const color = MARKETPLACE_PALETTE[binding.marketplace]
  const label = MARKETPLACE_LABELS[binding.marketplace]
  // Склад ФФ, которого нет в списке выбора (выключен или технический), всё
  // равно показывается своим названием — привязка к нему сохранена.
  const wmsOptions = wmsWarehouses.some((one) => one.id === binding.wmsWarehouseId)
    ? wmsWarehouses
    : [...wmsWarehouses, { id: binding.wmsWarehouseId, name: binding.wmsWarehouseName ?? `№ ${binding.wmsWarehouseId}` }]

  return (
    <Paper
      variant="outlined"
      sx={{ px: 2, pt: 1.5, pb: 1.75 }}
      data-testid={`fbs-stock-block-${binding.id}`}
      aria-label={binding.name}
    >
      <Stack
        direction="row"
        sx={{
          alignItems: 'center',
          flexWrap: 'wrap',
          columnGap: 2,
          rowGap: 1,
          pb: 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Stack
          direction="row"
          sx={{ alignItems: 'center', flexWrap: 'wrap', columnGap: 1.5, rowGap: 0.75, flex: '1 1 380px', minWidth: 0 }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
            <MarketplaceIcon marketplace={binding.marketplace} />
            <Typography sx={{ fontWeight: 600, fontSize: 16, overflowWrap: 'anywhere' }}>
              {binding.name}
            </Typography>
            {/* Номер вместо названия — не название (WMS-457). Чип говорит,
                почему имени нет: склада нет в кабинете либо список кабинета
                не получен, и причина — в сообщении выше. */}
            {binding.nameIssue ? (
              <StatusChip
                label={WAREHOUSE_NAME_ISSUE_LABELS[binding.nameIssue]}
                tone="warn"
                hint={warehouseNameIssueHint(binding.nameIssue, binding.marketplace)}
                testId={`fbs-stock-name-issue-${binding.id}`}
              />
            ) : null}
          </Stack>
          <Typography color="text.secondary" aria-hidden>↔</Typography>
          <Box sx={{ width: 260, maxWidth: '100%' }}>
            <SelectInput
              label="Склад ФФ"
              value={binding.wmsWarehouseId}
              onChange={(value) => {
                if (value && value !== binding.wmsWarehouseId) onChangeWmsWarehouse(value)
              }}
              options={wmsOptions.map((one) => ({ value: one.id, label: one.name }))}
              disabled={!editable || busy}
              testId={`fbs-stock-bind-${binding.id}`}
            />
          </Box>
        </Stack>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ ml: 'auto', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}
          data-testid={`fbs-stock-totals-${binding.id}`}
        >
          на складе {NUMBER_FORMAT(totals.onHand)} шт, занято {NUMBER_FORMAT(totals.reserved)} — свободно{' '}
          <Box component="b" sx={{ color: 'text.primary' }}>{NUMBER_FORMAT(totals.free)}</Box>
        </Typography>
      </Stack>

      <Stack direction="row" sx={{ alignItems: 'center', flexWrap: 'wrap', columnGap: 1.5, pt: 0.5 }}>
        {/* Галочка приёма заказов — свойство продавца, а не товара, но живёт
            здесь же: оператор видит склады продавца именно в этом окне.
            На публикацию остатка она не влияет — той управляет переключатель
            строки ниже (WMS-376). */}
        <CheckboxInput
          label={`Принимаем заказы продавца со склада «${binding.name}»`}
          checked={binding.served}
          onChange={onServedChange}
          disabled={!editable || busy}
          testId={`fbs-stock-served-${binding.id}`}
        />
        {!binding.served ? (
          <StatusChip
            label="заказы не принимаем"
            hint="Заказы продавца с этого склада к нам не приходят"
            testId={`fbs-stock-not-served-${binding.id}`}
          />
        ) : null}
      </Stack>

      {binding.served ? (
        <Box sx={{ pt: 0.5 }} data-testid={`fbs-stock-row-${binding.id}`}>
          <FormControlLabel
            sx={{ ml: -1, '& .MuiFormControlLabel-label': { display: 'inline-flex', alignItems: 'center', gap: 1, fontSize: 16 } }}
            control={
              <Switch
                checked={draft.publish}
                disabled={busy}
                onChange={(event) => onDraft({ ...draft, publish: event.target.checked })}
                sx={{
                  '& .MuiSwitch-switchBase.Mui-checked': { color },
                  '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: color },
                }}
                slotProps={{ input: { 'data-testid': `fbs-stock-publish-${binding.id}` } as never }}
              />
            }
            label={
              <>
                <span>Передавать остаток на</span>
                <MarketplaceIcon marketplace={binding.marketplace} />
                <Box component="span" sx={{ fontWeight: 600 }}>{label}</Box>
              </>
            }
          />
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr 52px', sm: 'minmax(160px, 1fr) 52px 132px auto' },
              alignItems: 'center',
              columnGap: 2,
              rowGap: 1,
              pl: { xs: 0, sm: 7.25 },
              minHeight: 44,
              opacity: draft.publish ? 1 : 0.42,
              pointerEvents: draft.publish ? 'auto' : 'none',
            }}
          >
            <Slider
              value={calc.pct}
              min={0}
              max={100}
              step={PERCENT_STEP}
              marks={Array.from({ length: 11 }, (_, i) => ({ value: i * 10 }))}
              // Процент показан числом справа от ползунка; всплывающая
              // подсказка над головкой наезжала бы на подпись переключателя.
              valueLabelDisplay="off"
              disabled={!draft.publish || busy}
              onChange={(_event, next) => {
                if (!draft.byPercent) return
                onDraft({ ...draft, percent: snapPercent(Array.isArray(next) ? next[0]! : next) })
              }}
              aria-label={`Доля свободного остатка на ${label}`}
              aria-readonly={!draft.byPercent}
              tabIndex={draft.byPercent ? 0 : -1}
              data-testid={`fbs-stock-percent-${binding.id}`}
              sx={{
                color,
                mx: 1,
                width: 'auto',
                '&.Mui-disabled': { color },
                // Ползунок-индикатор в ручном режиме: белая головка с цветной
                // обводкой, двигать нельзя.
                ...(draft.byPercent
                  ? {}
                  : {
                      pointerEvents: 'none',
                      '& .MuiSlider-thumb': { backgroundColor: 'common.white', border: '2px solid', borderColor: color },
                    }),
              }}
            />
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ textAlign: 'right', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}
              data-testid={`fbs-stock-pct-${binding.id}`}
            >
              {calc.pct} %
            </Typography>
            <TextField
              size="small"
              value={calc.fieldValue ?? ''}
              onChange={(event) => {
                if (draft.byPercent) return
                const digits = event.target.value.replace(/[^\d]/g, '')
                if (digits === '') {
                  onDraft({ ...draft, units: null })
                  onCapNote(null)
                  return
                }
                const { units, limitedBy } = clampUnits(binding, Number(digits), products)
                onDraft({ ...draft, units })
                onCapNote(limitedBy)
              }}
              disabled={!draft.publish || busy}
              slotProps={{
                htmlInput: {
                  inputMode: 'numeric',
                  pattern: '[0-9]*',
                  readOnly: draft.byPercent,
                  tabIndex: draft.byPercent ? -1 : 0,
                  'aria-label': `Штук на ${label}`,
                  'data-testid': `fbs-stock-units-${binding.id}`,
                  style: { textAlign: 'right' },
                },
                input: {
                  endAdornment: <InputAdornment position="end">шт</InputAdornment>,
                  sx: draft.byPercent ? { bgcolor: 'action.hover' } : undefined,
                },
              }}
            />
            <CheckboxInput
              label="процентом"
              checked={draft.byPercent}
              onChange={(byPercent) => {
                onDraft(toggleByPercent(binding, draft, byPercent, products))
                if (byPercent) onCapNote(null)
              }}
              disabled={!draft.publish || busy}
              testId={`fbs-stock-by-percent-${binding.id}`}
            />
            {capNote ? (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ gridColumn: '1 / -1', overflowWrap: 'anywhere', mt: -0.5 }}
                data-testid={`fbs-stock-cap-note-${binding.id}`}
              >
                {capNoteText(capNote)}
              </Typography>
            ) : null}
          </Box>
        </Box>
      ) : null}
    </Paper>
  )
}

function BindingPicker({
  picker,
  addable,
  wmsWarehouses,
  ozonWarehousesError,
  busy,
  onChange,
  onCancel,
}: {
  picker: Picker
  addable: CabinetWarehouse[]
  wmsWarehouses: Array<{ id: string; name: string }>
  ozonWarehousesError: string | null
  /** Идёт запись: выбор пары и отмена заперты, как и остальное окно. */
  busy: boolean
  onChange: (next: Picker) => void
  onCancel: () => void
}) {
  const keyOf = (one: CabinetWarehouse) => `${one.marketplace}:${one.externalId}`
  return (
    <Paper
      variant="outlined"
      sx={{ px: 2, py: 1.5, borderStyle: 'dashed' }}
      data-testid="fbs-stock-picker"
    >
      <Stack direction="row" sx={{ alignItems: 'center', flexWrap: 'wrap', columnGap: 2, rowGap: 1.5 }}>
        <TextField
          select
          size="small"
          label="Склад селлера"
          value={picker.warehouse ? keyOf(picker.warehouse) : ''}
          onChange={(event) => {
            const warehouse = addable.find((one) => keyOf(one) === event.target.value) ?? null
            onChange({ ...picker, warehouse })
          }}
          sx={{ width: 300, maxWidth: '100%' }}
          disabled={busy}
          slotProps={{
            inputLabel: { shrink: true },
            select: {
              displayEmpty: true,
              renderValue: (value) => {
                const warehouse = addable.find((one) => keyOf(one) === value)
                if (!warehouse) {
                  return <Box component="span" sx={{ color: 'text.secondary' }}>выберите склад из кабинета</Box>
                }
                return (
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
                    <MarketplaceIcon marketplace={warehouse.marketplace} />
                    <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{warehouse.name}</Box>
                  </Stack>
                )
              },
            },
            htmlInput: { 'data-testid': 'fbs-stock-picker-seller' },
          }}
          autoFocus
        >
          {addable.map((one) => (
            <MenuItem key={keyOf(one)} value={keyOf(one)} data-testid={`fbs-stock-picker-option-${keyOf(one)}`}>
              <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
                <MarketplaceIcon marketplace={one.marketplace} />
                <span>{one.name}</span>
              </Stack>
            </MenuItem>
          ))}
        </TextField>
        <Typography color="text.secondary" aria-hidden>↔</Typography>
        <Box sx={{ width: 300, maxWidth: '100%' }}>
          <SelectInput
            label="Склад ФФ"
            value={picker.wmsWarehouseId ?? ''}
            onChange={(value) => onChange({ ...picker, wmsWarehouseId: value || null })}
            options={wmsWarehouses.map((one) => ({ value: one.id, label: one.name }))}
            emptyLabel={picker.wmsWarehouseId ? undefined : 'выберите наш склад'}
            disabled={busy}
            testId="fbs-stock-picker-ff"
          />
        </Box>
        <IconButton
          size="small"
          aria-label="Не добавлять"
          onClick={onCancel}
          disabled={busy}
          sx={{ ml: 'auto' }}
          data-testid="fbs-stock-picker-cancel"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
        {/* Справочник одной из площадок не получен: её склады в списке не
            появятся, и без причины список выглядит просто коротким. */}
        {ozonWarehousesError ? (
          <Typography variant="caption" color="text.secondary" sx={{ width: '100%' }} data-testid="fbs-stock-ozon-directory-error">
            {ozonWarehousesError}
          </Typography>
        ) : null}
      </Stack>
    </Paper>
  )
}
