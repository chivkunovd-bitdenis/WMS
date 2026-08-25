import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded'
import MenuBookRounded from '@mui/icons-material/MenuBookRounded'
import {
  Box,
  Divider,
  Paper,
  Stack,
  Typography,
  useTheme,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { useNavigate } from 'react-router-dom'

import { PrimaryAction, ScreenHeader, StatusChip } from '../../ui-kit'

type Portal = 'seller' | 'ff'

type Callout = {
  left: string
  top: string
  width: string
  height: string
  label: string
}

type GuideStep = {
  number: number
  role: 'Селлер' | 'ФФ'
  title: string
  description: string
  actions: string[]
  result: string
  image: string
  imageAlt: string
  callout: Callout
}

const steps: GuideStep[] = [
  {
    number: 1,
    role: 'Селлер',
    title: 'Создайте новую приёмку',
    description:
      'Откройте раздел «Документы». Здесь хранятся черновики и уже переданные на склад приёмки.',
    actions: [
      'Нажмите «Создать заявку на поставку».',
      'Система сразу откроет новый черновик.',
    ],
    result: 'Появится форма новой приёмки со статусом «Черновик».',
    image: '/knowledge/inbound/01-seller-documents.jpg',
    imageAlt: 'Раздел документов селлера с выделенной кнопкой создания заявки на поставку',
    callout: {
      left: '21.6%',
      top: '25.8%',
      width: '20.2%',
      height: '6.7%',
      label: 'Нажмите эту кнопку',
    },
  },
  {
    number: 2,
    role: 'Селлер',
    title: 'Заполните план и передайте на склад',
    description:
      'Укажите, когда и что привезёте. Эти данные помогут складу заранее увидеть объём работы.',
    actions: [
      'Выберите дату и укажите количество грузомест.',
      'Добавьте товары и плановое количество каждого товара.',
      'Проверьте данные и нажмите «Передать на склад».',
    ],
    result: 'Документ исчезнет из черновиков и получит статус «Передано на склад».',
    image: '/knowledge/inbound/02-seller-inbound-form.jpg',
    imageAlt: 'Форма приёмки селлера с выделенной кнопкой передачи документа на склад',
    callout: {
      left: '82.5%',
      top: '28.7%',
      width: '14.5%',
      height: '6.6%',
      label: 'Передайте приёмку',
    },
  },
  {
    number: 3,
    role: 'ФФ',
    title: 'Найдите приёмку в очереди',
    description:
      'После передачи документ автоматически появляется у фулфилмента в разделе «Приёмка на FF».',
    actions: [
      'Найдите нужного селлера или номер документа.',
      'Убедитесь, что у новой строки статус «Передано». После начала работы он сменится на «Приёмка».',
      'Нажмите на строку, чтобы открыть документ.',
    ],
    result: 'Откроется карточка с планом по товарам и грузоместам.',
    image: '/knowledge/inbound/03-ff-reception-queue.jpg',
    imageAlt: 'Очередь приёмок на ФФ с выделенной строкой переданного документа',
    callout: {
      left: '22.1%',
      top: '71.7%',
      width: '76.1%',
      height: '5.5%',
      label: 'Откройте строку',
    },
  },
  {
    number: 4,
    role: 'ФФ',
    title: 'Зафиксируйте факт и завершите приёмку',
    description:
      'Начните приёмку, затем сканируйте товары или внесите фактическое количество вручную.',
    actions: [
      'Нажмите «Начать приёмку».',
      'Сканируйте штрихкоды: каждый успешный скан добавляет одну единицу.',
      'Сверьте план и факт, затем нажмите «Завершить приёмку».',
    ],
    result:
      'При совпадении приёмка завершится сразу. При расхождении система сначала попросит его подтвердить.',
    image: '/knowledge/inbound/04-ff-receiving-card.jpg',
    imageAlt: 'Карточка активной приёмки на ФФ с выделенной кнопкой завершения приёмки',
    callout: {
      left: '48.2%',
      top: '29.7%',
      width: '15.2%',
      height: '6.6%',
      label: 'Завершите приёмку',
    },
  },
]

function NumberBadge({ number }: { number: number }) {
  return (
    <Box
      aria-hidden="true"
      sx={{
        width: 34,
        height: 34,
        borderRadius: '50%',
        display: 'grid',
        placeItems: 'center',
        flex: '0 0 auto',
        bgcolor: 'primary.main',
        color: 'primary.contrastText',
        fontWeight: 900,
      }}
    >
      {number}
    </Box>
  )
}

function AnnotatedScreenshot({ step }: { step: GuideStep }) {
  return (
    <Box>
      <Box
        sx={{
          position: 'relative',
          overflow: 'hidden',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: 'background.default',
          boxShadow: '0 12px 28px rgba(15, 23, 42, 0.10)',
        }}
      >
        <Box
          component="img"
          src={step.image}
          alt={step.imageAlt}
          loading={step.number === 1 ? 'eager' : 'lazy'}
          data-testid={`knowledge-step-image-${step.number}`}
          sx={{ width: '100%', height: 'auto', display: 'block' }}
        />
        <Box
          aria-label={`${step.number}. ${step.callout.label}`}
          data-testid={`knowledge-step-callout-${step.number}`}
          sx={{
            position: 'absolute',
            left: step.callout.left,
            top: step.callout.top,
            width: step.callout.width,
            height: step.callout.height,
            border: '3px solid',
            borderColor: 'primary.main',
            borderRadius: 1.5,
            boxShadow: '0 0 0 4px rgba(255,255,255,0.88), 0 8px 22px rgba(91,33,182,0.22)',
            pointerEvents: 'none',
          }}
        >
          <Box
            sx={{
              position: 'absolute',
              left: -15,
              top: -15,
              width: 30,
              height: 30,
              borderRadius: '50%',
              display: 'grid',
              placeItems: 'center',
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              border: '3px solid white',
              fontSize: 14,
              fontWeight: 900,
            }}
          >
            {step.number}
          </Box>
        </Box>
      </Box>
      <Stack direction="row" spacing={1} sx={{ mt: 1.25, alignItems: 'center' }}>
        <NumberBadge number={step.number} />
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {step.callout.label}
        </Typography>
      </Stack>
    </Box>
  )
}

function StepSection({ step }: { step: GuideStep }) {
  return (
    <Box component="section" data-testid={`knowledge-step-${step.number}`} sx={{ py: { xs: 3, md: 4 } }}>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: 'minmax(260px, 0.76fr) minmax(0, 1.64fr)' },
          gap: { xs: 2.5, lg: 4 },
          alignItems: 'start',
        }}
      >
        <Stack spacing={2}>
          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
            <NumberBadge number={step.number} />
            <Box>
              <StatusChip label={step.role} tone={step.role === 'Селлер' ? 'neutral' : 'warn'} />
              <Typography variant="h6" sx={{ mt: 0.75, fontWeight: 800, lineHeight: 1.2 }}>
                {step.title}
              </Typography>
            </Box>
          </Stack>
          <Typography color="text.secondary">{step.description}</Typography>
          <Stack component="ol" spacing={1.25} sx={{ pl: 2.75, m: 0 }}>
            {step.actions.map((action) => (
              <Typography component="li" variant="body2" key={action} sx={{ pl: 0.5 }}>
                {action}
              </Typography>
            ))}
          </Stack>
          <Stack
            direction="row"
            spacing={1}
            sx={{
              alignItems: 'flex-start',
              p: 1.5,
              borderRadius: 2,
              bgcolor: (theme) => alpha(theme.palette.success.main, 0.08),
              color: 'success.dark',
            }}
          >
            <CheckCircleRounded fontSize="small" sx={{ mt: 0.15, flex: '0 0 auto' }} />
            <Typography variant="body2" sx={{ fontWeight: 650 }}>
              {step.result}
            </Typography>
          </Stack>
        </Stack>
        <AnnotatedScreenshot step={step} />
      </Box>
    </Box>
  )
}

export function KnowledgeBaseScreen({ portal }: { portal: Portal }) {
  const navigate = useNavigate()
  const theme = useTheme()
  const workPath = portal === 'seller' ? '../documents' : '/app/ff/reception'
  const workLabel = portal === 'seller' ? 'Открыть документы' : 'Открыть приёмку'

  return (
    <Box sx={{ width: '100%', minWidth: 0, maxWidth: 1260, mx: 'auto' }} data-testid="knowledge-base-page">
      <ScreenHeader
        title="База знаний"
        purpose="Пошаговые инструкции по работе в Короб ВМС — на настоящих экранах системы."
      />

      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        <Box
          sx={{
            px: { xs: 2, md: 4 },
            py: { xs: 3, md: 4 },
            background: `linear-gradient(125deg, ${alpha(theme.palette.primary.main, 0.16)} 0%, ${alpha(theme.palette.primary.main, 0.04)} 58%, ${theme.palette.background.paper} 100%)`,
          }}
        >
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} sx={{ justifyContent: 'space-between' }}>
            <Box sx={{ maxWidth: 760 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5 }}>
                <MenuBookRounded color="primary" />
                <Typography variant="overline" color="primary.main" sx={{ fontWeight: 900, letterSpacing: 1.1 }}>
                  Инструкция · 7 минут
                </Typography>
              </Stack>
              <Typography
                variant="h4"
                component="h1"
                sx={{ fontWeight: 900, lineHeight: 1.12, color: 'text.primary' }}
              >
                Создание приёмки: от селлера до ФФ
              </Typography>
              <Typography color="text.secondary" sx={{ mt: 1.5, maxWidth: 660 }}>
                Селлер передаёт план на склад, сотрудник ФФ принимает товар по факту. Четыре шага —
                без лишних настроек и переходов. Экраны сняты на актуальном стенде WMS.
              </Typography>
            </Box>
            <Stack spacing={1.25} sx={{ minWidth: { md: 250 }, alignSelf: { md: 'center' } }}>
              {['Создать черновик', 'Передать на склад', 'Открыть на ФФ', 'Завершить приёмку'].map(
                (label, index) => (
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} key={label}>
                    <Box
                      sx={{
                        width: 24,
                        height: 24,
                        borderRadius: '50%',
                        display: 'grid',
                        placeItems: 'center',
                        bgcolor: index === 3 ? 'success.main' : 'primary.main',
                        color: index === 3 ? 'success.contrastText' : 'primary.contrastText',
                        fontWeight: 800,
                        fontSize: 12,
                      }}
                    >
                      {index + 1}
                    </Box>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {label}
                    </Typography>
                  </Stack>
                ),
              )}
            </Stack>
          </Stack>
        </Box>

        <Box sx={{ px: { xs: 2, md: 4 } }}>
          {steps.map((step, index) => (
            <Box key={step.number}>
              {index > 0 ? <Divider /> : null}
              <StepSection step={step} />
            </Box>
          ))}
        </Box>

        <Divider />
        <Box sx={{ px: { xs: 2, md: 4 }, py: 3, bgcolor: (t) => alpha(t.palette.primary.main, 0.05) }}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
          >
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 800 }}>
                Можно начинать
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Откройте рабочий раздел и повторите шаги на своей приёмке.
              </Typography>
            </Box>
            <PrimaryAction
              onClick={() => navigate(workPath)}
              endIcon={<ArrowForwardRounded />}
              data-testid="knowledge-open-workflow"
            >
              {workLabel}
            </PrimaryAction>
          </Stack>
        </Box>
      </Paper>
    </Box>
  )
}
