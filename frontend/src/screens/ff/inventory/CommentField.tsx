import { useEffect, useRef, useState } from 'react'
import { TextInput } from '../../../ui-kit'

// Комментарий держит значение у себя и отдаёт наверх, когда человек перестал
// печатать.
//
// Почему не напрямую в документ: каждая буква меняла бы документ целиком, а от
// него пересчитывается всё дерево и перерисовывается экран под ним — на карте
// склада это три десятка строк с перетаскиванием. Печатать в такое поле
// невозможно, буквы догоняют через секунду. Наверх уходит готовая фраза.
const COMMIT_DELAY_MS = 400

type Props = {
  value: string
  onCommit: (value: string) => void
  disabled?: boolean
  helperText?: string
  testId?: string
}

export function CommentField({ value, onCommit, disabled, helperText, testId }: Props) {
  const [draft, setDraft] = useState(value)
  // Держим последнюю функцию в ссылке: иначе таймер поднимет наверх фразу через
  // ту версию обработчика, что была на момент нажатия клавиши, и потеряет её.
  const commitRef = useRef(onCommit)
  commitRef.current = onCommit

  // Документ сменился снаружи — открыли другой, вернулись к списку. Своё
  // черновое значение в таком случае не держим: оно относилось к прошлому.
  useEffect(() => {
    setDraft(value)
  }, [value])

  useEffect(() => {
    if (draft === value) return
    const timer = setTimeout(() => commitRef.current(draft), COMMIT_DELAY_MS)
    return () => clearTimeout(timer)
  }, [draft, value])

  return (
    <TextInput
      label="Комментарий"
      value={draft}
      onChange={setDraft}
      disabled={disabled}
      helperText={helperText}
      testId={testId}
    />
  )
}
