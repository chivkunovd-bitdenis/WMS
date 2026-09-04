import { useCallback, useEffect, useRef, useState } from 'react'
import { Box, Paper, Stack, Typography } from '@mui/material'
import { CheckboxInput, ErrorNotice, PrimaryAction, SelectInput } from '../../ui-kit'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  DEFAULT_PRINT_LABEL_OPTIONS,
  resolvePrintTemplate,
  type PrintLabelOptions,
} from '../../utils/printTemplate'

type SellerOption = { id: string; name: string }

const FIELDS: Array<{ key: keyof PrintLabelOptions; label: string }> = [
  { key: 'include_size', label: 'Размер' },
  { key: 'include_color', label: 'Цвет' },
  { key: 'include_brand', label: 'Бренд' },
  { key: 'include_composition', label: 'Состав' },
]

/**
 * Состав этикетки ШК, закреплённый за продавцом.
 *
 * До 03.09.2026 настроить это было нельзя: хранилище шаблонов с привязкой к
 * продавцу существовало, но хранило только ленту печати, а состав самой
 * этикетки жил в момент печати и забывался. Порядок строк единый для всех и
 * здесь не настраивается — только что показывать, а что нет.
 */
export function FfLabelTemplatePanel({ token }: { token: string }) {
  const [sellers, setSellers] = useState<SellerOption[]>([])
  const [sellerId, setSellerId] = useState('')
  const [options, setOptions] = useState<PrintLabelOptions>(DEFAULT_PRINT_LABEL_OPTIONS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  // Рубильник сборки. Пока он выключен, состав этикетки не настраивается вовсе
  // и панели нет: боевая сборка не должна иметь ни одной возможности повлиять
  // на то, что печатается сегодня.
  const [enabled, setEnabled] = useState<boolean | null>(null)

  // Ответ на прошлого продавца не должен записываться в галочки нового.
  // Переключились с А на Б, ответ А пришёл позже — и оператор сохранил бы
  // настройки А под именем Б, ничего не заметив.
  const requestedSellerRef = useRef('')

  const load = useCallback(async (id: string) => {
    setError(null)
    setSaved(false)
    requestedSellerRef.current = id
    try {
      const template = await resolvePrintTemplate(token, { sellerId: id })
      if (requestedSellerRef.current !== id) return
      setOptions(template.layout.label_options ?? DEFAULT_PRINT_LABEL_OPTIONS)
    } catch (cause) {
      if (requestedSellerRef.current !== id) return
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить настройку')
    }
  }, [token])

  useEffect(() => {
    if (enabled !== true) return
    void (async () => {
      try {
        const response = await fetch(apiUrl('/sellers'), {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) return
        const rows = (await response.json()) as SellerOption[]
        setSellers(rows)
      } catch {
        // Список продавцов не загрузился — панель просто останется пустой,
        // ронять весь экран настроек из-за неё нельзя.
      }
    })()
  }, [token, enabled])

  useEffect(() => {
    void (async () => {
      try {
        const response = await fetch(apiUrl('/tenant/settings'), {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) {
          setEnabled(false)
          return
        }
        const data = (await response.json()) as { label_template_enabled?: boolean }
        setEnabled(data.label_template_enabled === true)
      } catch {
        // Не смогли спросить — считаем выключенным. Показать панель, которой
        // сервер не даст сохранить, хуже, чем не показать ничего.
        setEnabled(false)
      }
    })()
  }, [token])

  useEffect(() => {
    if (sellerId) void load(sellerId)
  }, [sellerId, load])

  const save = async () => {
    if (!sellerId) return
    setBusy(true)
    setError(null)
    try {
      // Отдельная ручка состава: она меняет только галочки и не трогает ленту
      // печати продавца. Пока панель сохраняла шаблон целиком, она заодно
      // переписывала ленту на «один ШК», и у оператора без личной раскладки
      // из печати пропадал Честный знак.
      const response = await fetch(
        apiUrl('/operations/marking-codes/print-templates/seller-label-options'),
        {
          method: 'PUT',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ seller_id: sellerId, label_options: options }),
        },
      )
      if (!response.ok) throw new Error(await readApiErrorMessage(response))
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить')
    } finally {
      setBusy(false)
    }
  }

  if (enabled !== true) {
    return null
  }

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3 }} data-testid="ff-settings-label-panel">
      <Typography variant="subtitle1" gutterBottom>
        Этикетка товара
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Что печатать на этикетке ШК у этого продавца. Порядок строк единый для всех: размер,
        цвет, бренд, состав. Пустые поля товара не печатаются в любом случае.
      </Typography>
      <Stack spacing={2}>
        <Box sx={{ maxWidth: 320 }}>
          <SelectInput
            label="Продавец"
            value={sellerId}
            onChange={setSellerId}
            emptyLabel="Выберите продавца"
            options={sellers.map((one) => ({ value: one.id, label: one.name }))}
            testId="ff-label-seller"
          />
        </Box>
        {sellerId ? (
          <>
            <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
              {FIELDS.map((field) => (
                <CheckboxInput
                  key={field.key}
                  label={field.label}
                  checked={options[field.key]}
                  onChange={(checked: boolean) => {
                    setSaved(false)
                    setOptions((prev) => ({ ...prev, [field.key]: checked }))
                  }}
                  testId={`ff-label-${field.key}`}
                />
              ))}
            </Stack>
            <Box>
              <PrimaryAction
                onClick={() => void save()}
                disabledReason={busy ? 'Сохраняется' : undefined}
                data-testid="ff-label-save"
              >
                Сохранить
              </PrimaryAction>
            </Box>
            {saved ? (
              <Typography variant="body2" color="success.main" data-testid="ff-label-saved">
                Сохранено: так теперь печатаются этикетки этого продавца.
              </Typography>
            ) : null}
          </>
        ) : null}
        {error ? <ErrorNotice testId="ff-label-error">{error}</ErrorNotice> : null}
      </Stack>
    </Paper>
  )
}
