# WMS-672: bounded read-only observation после Linux отказа

**Исправление окна 32→16 не закрыло C5; product-reference upgrade не одобрен.**
Этот результат дополняет исторический source-only PASS: техническое чтение diff
не являлось доказательством эффективности или готовности продукта.

Прочитаны сохранённые Linux141 события run `37529471517` attempt 1 в evidence
`85de599e0` / общем источнике `67ed830a18fd9eea0ea41d3e294885f7b82c3c71`,
`native-decode-fix-linux-comparison-20261007/raw/672/fixture-2/page-0.json`,
summary/receipt и diagnostic adapter из run head
`68207fee941e7682adbc1c0ac31f366aeeff044c`. Новых запусков или правок продукта нет.

При injected 299 Promise catch имеет started=300, decoded=288; сразу затем
recorded iframe-remove и screen-catch имеют те же значения. Frozen test wrapper
повышает started перед injected branch, но повышает decoded только после
успешного await native decode. Для injected 299 native decode не вызывается.
Для остальных 11 этой последней группы (289–298 и 300) native-start записан.
Следовательно, на границе удаления не зарегистрированы успешные завершения
этих 11 outer wrappers. Код Promise.all действительно не дожидается peers после
первого rejection, и cleanup вызывается из catch этого первого отказа.

**Что этим не доказано:** observer записывает native-start и native-reject,
но native fulfillment или универсальный settlement не записывает. Счётчик decoded
не является счётчиком внутренних ресурсов декодера. По нему нельзя различить
ещё работающий native decode, уже завершённый native decode с необработанной
continuation, cancellation при удалении realm или навсегда незавершённую promise.
Время performance.now берётся из разных realms; сравнивать абсолютные iframe
и parent timestamps для расчёта общей длительности нельзя. Общий event array
и parent события дают порядок наблюдаемого удаления/catch.

В исправленном retry отказ на cumulative invocation 531 соответствует retry
label 231. Same identity 2 переносится native-reject → promise-catch → screen-catch,
сообщение сохранено; parent instanceof Error=false. На отказе PNG имеет
complete=true, natural 836×356; saved offline decode подтверждает корректный PNG
и код INB-000000000231. Итог started=540/decoded=518, transfer=0, iframe=0;
GET-only requests подтверждают отсутствие marks, но не причину Chromium отказа.

**Контрусловие причинному выводу:** fixture-1 injected 150 тоже удаляет iframe при
160 started/144 decoded: 15 noninjected peers не имеют зарегистрированного success
на этой границе. При этом corrected retry300, ordered renderTape и all300 marks
успешны; итог decoded=444=144+300. Значит раннее удаление при таких peers само по
себе не является достаточным условием последующего отказа. Оно остаётся конкретной
технической гипотезой о lifecycle, а не установленной причиной retry231.

Осмысленный held-peer контракт может фиксировать отсутствие следующей decode
группы, print/source save/marks после первой ошибки, сохранение её причины и
границу cleanup относительно settling уже начатых peers. Он не докажет здоровье
Chromium без отдельного actual Linux counterfactual на exact source. Числовое
окно, timeout и исходный C5 в этой независимой проверке не менялись.
Наблюдения и контрусловие переданы разработчику; дальнейший контракт/реализация
принадлежат отдельным ролям. По просьбе ведущего сессия освобождает слот.
