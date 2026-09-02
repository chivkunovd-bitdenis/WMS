import { useCallback, useEffect, useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'

import {
  ActionGroup,
  AppDialog,
  ErrorNotice,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  TextInput,
} from '../../ui-kit'

/**
 * Реквизиты фулфилмента и селлеров.
 *
 * Модель реквизитов и эндпоинты в системе были с самого начала, а формы не было
 * ни одной: заполнить их из интерфейса было нельзя вообще, и в счёт они
 * попадать не могли. Здесь эта дыра и закрывается.
 *
 * ИНН подставляется из DaData: наименование, КПП и адрес приезжают сами.
 * Расчётный счёт не подставляется ничем — его нет в открытых данных, поэтому
 * банковский блок заполняется руками.
 */

type Seller = { id: string; name: string }

type ProfileForm = {
  legal_name: string
  inn: string
  kpp: string
  bank_name: string
  bik: string
  settlement_account: string
  correspondent_account: string
}

const EMPTY: ProfileForm = {
  legal_name: '',
  inn: '',
  kpp: '',
  bank_name: '',
  bik: '',
  settlement_account: '',
  correspondent_account: '',
}

const LOOKUP_ERRORS: Record<string, string> = {
  dadata_not_configured:
    'Подстановка по ИНН не настроена: администратору нужно задать ключ DaData в переменной DADATA_TOKEN',
  inn_invalid: 'Проверьте ИНН: должно быть 10 или 12 цифр с верной контрольной суммой',
  party_not_found: 'По этому ИНН организация не найдена',
  dadata_rejected: 'DaData отказала: ключ не принят или исчерпан дневной лимит',
  dadata_unavailable: 'DaData не ответила. Заполните реквизиты руками или повторите позже',
}

export function FfBillingProfilesDialog({
  token,
  sellers,
}: {
  token: string
  sellers: Seller[]
}) {
  const [open, setOpen] = useState(false)
  const [scope, setScope] = useState('ff')
  const [form, setForm] = useState<ProfileForm>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const path = scope === 'ff' ? '/api/billing/profiles/ff' : `/api/billing/profiles/sellers/${scope}`

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const response = await fetch(path, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('profile')
      const data = (await response.json()) as Partial<ProfileForm> | null
      setForm({ ...EMPTY, ...Object.fromEntries(Object.entries(data ?? {}).map(([key, value]) => [key, value ?? ''])) })
    } catch {
      setError('Не удалось загрузить реквизиты')
    } finally {
      setBusy(false)
    }
  }, [path, token])

  useEffect(() => {
    if (!open) return
    void load()
  }, [load, open])

  const field = (key: keyof ProfileForm) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }))

  async function lookupByInn() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const response = await fetch(
        `/api/billing/profiles/lookup-inn?inn=${encodeURIComponent(form.inn.trim())}`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      const data = (await response.json()) as Record<string, string | null>
      if (!response.ok) {
        setError(LOOKUP_ERRORS[String(data.detail)] ?? 'Подстановка по ИНН не сработала')
        return
      }
      setForm((current) => ({
        ...current,
        legal_name: data.legal_name ?? current.legal_name,
        inn: data.inn ?? current.inn,
        kpp: data.kpp ?? current.kpp,
      }))
      setNotice(
        [data.legal_name, data.address, data.manager ? `Руководитель: ${data.manager}` : null]
          .filter(Boolean)
          .join(' · '),
      )
    } catch {
      setError('Подстановка по ИНН не сработала')
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(path, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          legal_name: form.legal_name.trim(),
          inn: form.inn.trim(),
          kpp: form.kpp.trim() || null,
          bank_name: form.bank_name.trim() || null,
          bik: form.bik.trim() || null,
          settlement_account: form.settlement_account.trim() || null,
          correspondent_account: form.correspondent_account.trim() || null,
        }),
      })
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string }
        setError(String(data.detail ?? 'Реквизиты не сохранены'))
        return
      }
      setNotice('Реквизиты сохранены')
    } catch {
      setError('Реквизиты не сохранены')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <SecondaryAction onClick={() => setOpen(true)} data-testid="billing-profiles-open">
        Реквизиты
      </SecondaryAction>
      <AppDialog
        open={open}
        title="Реквизиты для счетов"
        onClose={() => setOpen(false)}
        maxWidth="md"
        testId="billing-profiles"
        actions={
          <ActionGroup>
            <PrimaryAction
              onClick={() => void save()}
              disabledReason={
                !form.legal_name.trim() || !form.inn.trim()
                  ? 'Наименование и ИНН обязательны'
                  : busy
                    ? 'Идёт запрос'
                    : undefined
              }
              data-testid="billing-profiles-save"
            >
              Сохранить
            </PrimaryAction>
            <SecondaryAction onClick={() => setOpen(false)}>Закрыть</SecondaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <SelectInput
            label="Чьи реквизиты"
            value={scope}
            onChange={setScope}
            options={[
              { value: 'ff', label: 'Наши — фулфилмент' },
              ...sellers.map((seller) => ({ value: seller.id, label: `Селлер · ${seller.name}` })),
            ]}
            testId="billing-profiles-scope"
          />
          <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
            <Box sx={{ width: 220, flexShrink: 0 }}>
              <TextInput
                label="ИНН"
                value={form.inn}
                onChange={field('inn')}
                testId="billing-profiles-inn"
              />
            </Box>
            <SecondaryAction
              onClick={() => void lookupByInn()}
              disabledReason={
                form.inn.trim().length < 10 ? 'Введите ИНН — 10 или 12 цифр' : busy ? 'Идёт запрос' : undefined
              }
              data-testid="billing-profiles-lookup"
            >
              Заполнить по ИНН
            </SecondaryAction>
          </Stack>
          <TextInput
            label="Наименование"
            value={form.legal_name}
            onChange={field('legal_name')}
            testId="billing-profiles-name"
          />
          <Stack direction="row" spacing={1}>
            <Box sx={{ width: 220 }}>
              <TextInput label="КПП" value={form.kpp} onChange={field('kpp')} testId="billing-profiles-kpp" />
            </Box>
            <Box sx={{ flex: 1 }}>
              <TextInput
                label="Банк"
                value={form.bank_name}
                onChange={field('bank_name')}
                testId="billing-profiles-bank"
              />
            </Box>
            <Box sx={{ width: 180 }}>
              <TextInput label="БИК" value={form.bik} onChange={field('bik')} testId="billing-profiles-bik" />
            </Box>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Box sx={{ flex: 1 }}>
              <TextInput
                label="Расчётный счёт"
                value={form.settlement_account}
                onChange={field('settlement_account')}
                testId="billing-profiles-account"
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <TextInput
                label="Корреспондентский счёт"
                value={form.correspondent_account}
                onChange={field('correspondent_account')}
                testId="billing-profiles-corr"
              />
            </Box>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Расчётный счёт по ИНН не подставляется: его нет в открытых данных. Наименование, КПП и
            адрес приезжают сами.
          </Typography>
          {notice ? (
            <Typography variant="body2" data-testid="billing-profiles-notice">
              {notice}
            </Typography>
          ) : null}
          {error ? <ErrorNotice testId="billing-profiles-error">{error}</ErrorNotice> : null}
        </Stack>
      </AppDialog>
    </>
  )
}
