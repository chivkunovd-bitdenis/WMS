package ru.wms.tsd.core.scanner

import android.view.KeyEvent

/**
 * Распознаёт ввод сканера в режиме keyboard wedge: сканер «печатает» штрихкод
 * очень быстро и завершает Enter'ом. Человек так печатать не может, поэтому
 * критерий — межсимвольный интервал не больше [maxInterKeyMs].
 *
 * ВАЖНО: аккумулятор ПАССИВНЫЙ — символы не потребляет (они доходят до UI,
 * например до полей логина), потребляется только Enter завершившегося скана.
 * Урок T-18: жадное потребление символов ломало ввод в текстовые поля
 * (быстрый ввод adb/автозаполнения неотличим от сканера).
 *
 * Подключается в MainActivity.dispatchKeyEvent: если feed() вернул true,
 * событие (Enter) потреблено и в UI не уходит.
 */
class WedgeKeyAccumulator(
    private val manager: ScannerManager,
    private val minLength: Int = 4,
    private val maxInterKeyMs: Long = 60,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val buffer = StringBuilder()
    private var lastKeyAt = 0L
    private var consumeNextEnterUp = false

    fun feed(event: KeyEvent): Boolean {
        if (event.action == KeyEvent.ACTION_UP) {
            if (event.keyCode == KeyEvent.KEYCODE_ENTER && consumeNextEnterUp) {
                consumeNextEnterUp = false
                return true
            }
            return false
        }
        if (event.action != KeyEvent.ACTION_DOWN) return false

        if (event.keyCode == KeyEvent.KEYCODE_ENTER) {
            val consumed = feedEnter(now())
            consumeNextEnterUp = consumed
            return consumed
        }
        val ch = event.unicodeChar
        if (ch != 0) feedChar(ch.toChar(), now())
        return false // символы всегда доходят до UI
    }

    /** Накопление кандидата в скан. Ничего не потребляет. */
    fun feedChar(ch: Char, timeMs: Long) {
        if (buffer.isNotEmpty() && timeMs - lastKeyAt > maxInterKeyMs) {
            // Пауза как у человека — это не сканер; накопленное сбрасываем.
            buffer.clear()
        }
        buffer.append(ch)
        lastKeyAt = timeMs
    }

    /** @return true, если Enter завершил скан (штрихкод отправлен в ScannerManager). */
    fun feedEnter(timeMs: Long): Boolean {
        val text = buffer.toString()
        val gap = timeMs - lastKeyAt
        buffer.clear()
        if (text.length >= minLength && gap <= maxInterKeyMs) {
            manager.submit(text, ScanSource.KEYBOARD_WEDGE)
            return true
        }
        return false
    }
}
