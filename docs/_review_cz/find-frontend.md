# Ревью фронтенда (ЧЗ) — find-frontend

## Резюме
Найдено 2 находки: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 1 LOW. Раскладка печати (главный инвариант — пара одинаковых КМ внутри единицы, следующий код между разными единицами) реализована КОРРЕКТНО. Секретов на фронте нет. Самое заметное (MEDIUM) — в списке строк упаковки нехватка кодов не подсвечивается визуально (нет warning-цвета/баннера) до открытия диалога печати, хотя в самом диалоге и в превью «печать всех» — подсвечивается.

---

## Что проверено и почему ОК (по критическим пунктам)

### 1. Раскладка печати — КОРРЕКТНО (главный инвариант)
- **Где:** `frontend/src/utils/markingPrintPresets.ts:51-64` (`expandLayoutTape`), `frontend/src/utils/printMarkingCodeLabel.ts:222-261` (`printMarkingCodeTape`), `frontend/src/utils/markingPrintPresets.test.ts:5-28`.
- **Доказательство:**
```ts
// markingPrintPresets.ts
for (let i = 0; i < codes.length; i += 1) {
  const cis = codes[i]
  for (const unit of units) {
    const copies = Math.max(1, unit.copies)
    for (let c = 0; c < copies; c += 1) {
      out.push({ block: unit.block, cis, unitIndex: i })
    }
  }
}
```
Внешний цикл — по кодам (единицам товара), внутренний — по копиям одного и того же `cis`. То есть один и тот же КМ повторяется подряд внутри единицы, а СЛЕДУЮЩИЙ (другой) код начинается на следующей итерации внешнего цикла — ровно между разными единицами. Пресет «Парами (реком.)» = `{ block: 'cz', copies: 2 }` (`markingPrintPresets.ts:11-16`) даёт `[ЧЗ-A][ЧЗ-A] [ЧЗ-B][ЧЗ-B]`. Юнит-тест это фиксирует: `cz:cis-a, cz:cis-a, label:cis-a, cz:cis-b, cz:cis-b, label:cis-b`. Соответствует DESIGN `CHESTNY_ZNAK_DESIGN_RU.md:35` («пара «код на товар + такой же на пакет», дальше следующий код») и `:294` (на единицу `[ЧЗ][ЧЗ]`). Все пути печати (диалог `MarkingPrintDialog.tsx:204`, скан-печать `FfPackagingPage.tsx:423`, печать-всех) используют `printMarkingCodeLabels`→`expandLayoutTape`. **Нарушений порядка нет.**

### 3. Секреты не на фронте — ОК
- **Где:** `grep -rniE "fernet|secret_key|jwt_secret|sk_live|-----BEGIN|encryption_key" frontend/src` — пусто.
- Учётные данные маркировки на фронте представлены только булевыми флагами наличия: `frontend/src/screens/v2/SellerSettingsScreen.tsx:30-41` (`has_cz_token`, `has_suz_oms_token`, `has_mp_api_key` — не сами токены). При загрузке (`loadMarkingCredentials`, `:104-124`) сами секреты с бэка не приходят. Токен авторизации берётся из storage (`getStoredToken`) и идёт в заголовок `Authorization` — это нормально, не зашитый секрет. **Утечки нет.**

### 2 (частично). Индикатор нехватки в диалоге печати — ЕСТЬ
- **Где:** `frontend/src/components/MarkingPrintDialog.tsx:104, 288-292`.
- Красный баннер `Alert severity="error"` «Не хватает {shortage} из {qtyNeed} кодов» рассчитывается из `ctx` сразу при рендере (открытии) диалога — соответствует DESIGN `:36`/`:292`. Также есть чекбокс «Печатать доступные N» и кнопка «Запросить у селлера». Превью «печать всех» подсвечивает строки с нехваткой (`FfPackagingPage.tsx:844-848`).

### 4. Единый MUI — в целом ОК
- Компоненты ЧЗ используют общий MUI-кит (`Dialog/Alert/Chip/RadioGroup/TextField/Button` из `@mui/material`). Самописных кнопок/инпутов вместо темы не обнаружено. Печатные шаблоны (`printMarkingCodeLabel.ts`) — это генерация HTML для термопринтера в iframe, инлайновый CSS здесь оправдан (печать вне React-дерева), не нарушение дизайн-кита.

---

## [MEDIUM] В списке строк упаковки нехватка кодов не подсвечивается до открытия диалога
- **Где:** `frontend/src/screens/ff/FfPackagingPage.tsx:656-668`
- **Доказательство:**
```tsx
{ln.requires_honest_sign ? (
  <Stack spacing={0.25} sx={{ alignItems: 'flex-end' }}>
    <Typography variant="caption" color="text.secondary">
      {ln.qty_marking_printed > 0
        ? `напеч. ${ln.qty_marking_printed}`
        : `дост. ${ln.marking_available_count}`}
    </Typography>
  </Stack>
) : (
  '—'
)}
```
- **Проблема:** Ячейка ЧЗ показывает «дост. N» всегда нейтральным `text.secondary`, без сравнения с `qty_need_pack`. Когда `marking_available_count < qty_need_pack` (нехватка по строке), оператор НЕ видит предупреждения в самом списке — узнаёт только открыв диалог печати. DESIGN `CHESTNY_ZNAK_DESIGN_RU.md:36` требует подсвечивать нехватку «**сразу**», а `:378` — «ранняя подсветка нехватки при создании упаковки». Внутри же превью «печать всех» нехватка корректно красится (`:844` `color={ln.shortage > 0 ? 'warning.main' : ...}`) — то есть данные для подсветки есть, но в основном списке строк они не применяются. Это непоследовательность относительно собственного же паттерна.
- **Фикс:** В ячейке (`:659-663`) при `ln.marking_available_count < ln.qty_need_pack` (и `qty_marking_printed < 1`) красить текст в `warning.main`/`error.main` и добавить подпись вида «не хватает {qty_need_pack - marking_available_count}», по аналогии с превью «печать всех». Опционально — иконка/Chip warning на строке.

---

## [LOW] Reprint никогда не показывает нехватку кодов в пуле
- **Где:** `frontend/src/components/MarkingPrintDialog.tsx:102-111, 253-257`
- **Доказательство:**
```tsx
const qtyNeed = reprint ? (ctx?.qtyMarkingPrinted ?? 0) : (ctx?.qtyNeedPack ?? 0)
const available = ctx?.markingAvailable ?? 0
const shortage = !reprint && available < qtyNeed ? qtyNeed - available : 0
...
const printDisabled =
  busy ||
  qtyNeed < 1 ||
  (!reprint && available < 1) ||
  (!reprint && !allowPartial && shortage > 0)
```
- **Проблема:** Для повторной печати (`reprint=true`) `shortage` принудительно `0`, и кнопка «Перепечатать» не блокируется по доступности (`available`). Если перепечатка тянет коды из пула и кодов не хватает, фронт не предупредит заранее — пользователь увидит ошибку только после ответа бэка (`:196-202` «Не хватает … кодов ЧЗ в пуле»). Перепечатка по своей сути обычно использует уже выданные коды (поэтому это LOW, **требует подтверждения** контракта бэка `.../print` с `reprint:true`: берёт ли он коды из пула или переиспользует ранее напечатанные для строки). Если переиспользует — поведение корректно и находку можно закрыть.
- **Фикс (если перепечатка тянет из пула):** учитывать `available` и для `reprint` (показывать баннер нехватки и блокировать кнопку), либо явно отображать «коды берутся из ранее выданных» чтобы снять неоднозначность. Иначе — оставить как есть.
