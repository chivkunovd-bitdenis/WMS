import { useCallback, useEffect, useState } from 'react'
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

  const load = useCallback(async (id: string) => {
    setError(null)
    setSaved(false)
    try {
      const template = await resolvePrintTemplate(token, { sellerId: id })
      setOptions(template.layout.label_options ?? DEFAULT_PRINT_LABEL_OPTIONS)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить настройку')
    }
  }, [token])

  useEffect(() => {
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
  }, [token])

  useEffect(() => {
    if (sellerId) void load(sellerId)
  }, [sellerId, load])

  const save = async () => {
    if (!sellerId) return
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/operations/marking-codes/print-templates'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Этикетка продавца',
          seller_id: sellerId,
          is_default: true,
          layout: { units: [{ block: 'label', copies: 1 }], label_options: options },
        }),
      })
      if (!response.ok) throw new Error(await readApiErrorMessage(response))
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить')
    } finally {
      setBusy(false)
    }
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
