# WMS-399 — браузерная обратная связь автору

Компилятор после твоего исправления: typecheck PASS, Vite build PASS.
Координатор открыл настоящий отдельный Chrome на 127.0.0.1:5199,
нажимал UI-кнопки через браузерный инструмент. Runtime pageerror=[] в проверенных путях.
React координатор не менял. Сохрани композицию и исправь сам точечно:

1. **Счётчик обсуждения выдаёт скрытый ответ.** В default Приёмка IN-2926
   у оператора 3 seed-ответа, один internal. После переключения Селлер
   (Ловиана) текст внутреннего ответа правильно исчезает, но кнопка всё ещё
   `Обсуждение · 3`. После отправки ещё одного shared-ответа показывает 4,
   хотя видимы 3. Считай только ответы, доступные текущему актору, существующим
   selector; не добавляй отдельные хранимые счётчики. Проверь также notifications
   и previews на тот же принцип видимости, без новых сущностей.

2. **Мобильный composer.** Viewport390x844, роль seller, mobile mode:
   в нижней строке длинный `Селлеру виден` теснит кнопку `Отправить`, текст и
   кнопка пересекаются/обрезаются справа. Снимок mobile-conversation-20260909.png.
   Сохрани элементы, цвета и логику, уложи строку по ширине.

3. **Высота чата.** В default desktop1440x1000 body имеет около1606px;
   в mobile390x844 body1658px после нескольких synthetic сообщений.
   Composer в самом конце страницы ниже viewport; скроллится вся страница
   с шапкой вместо отдельной ленты. См desktop-20260909.png и mobile-conversation.
   Приведи viewport/flex min-height так, чтобы header/composer оставались
   видимыми, скроллилась история, а панели контекста/ветки тоже могли прокручиваться.
   Не меняй дизайн, исправь размеры и overflow.

Уже проверены send, thread reply, lightbox open/close, document preview,
picker search F-880 + insert/send, participants(operator invite disabled),
search недовоз → URL сообщения, notifications/read-all, preferences mentions/digest,
role→seller hides internal text/channel/thread, mobile inbox→channel, offline failed
send→retry, outdated docs, denied403, attachment synthetic27byte file failure→retry.
Не утверждай весь browser pass завершён; после твоего прохода координатор повторит
проблемные случаи и остальные состояния. Не запускай Bash/browser/build.
Все ограничения COORDINATOR_RESUME сохраняются.
