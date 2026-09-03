package ru.wms.tsd.core.scanner

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build

/**
 * Известные broadcast-интенты аппаратных сканеров ТСД.
 * Формат: action → список extra-ключей, в которых производители кладут штрихкод
 * (проверяются по порядку, берётся первый непустой).
 *
 * Новую модель ТСД поддерживаем добавлением строки сюда — код экранов не меняется.
 */
private val KNOWN_SCANNER_BROADCASTS: Map<String, List<String>> = mapOf(
    // Urovo
    "android.intent.ACTION_DECODE_DATA" to listOf("barcode_string", "barcode"),
    // Zebra DataWedge (intent output настраивается в профиле DataWedge на устройстве;
    // используем общепринятый кастомный action)
    "com.zebra.datawedge.SCAN" to listOf("com.symbol.datawedge.data_string"),
    // Chainway
    "com.scanner.broadcast" to listOf("data", "SCAN_BARCODE1"),
    // Honeywell (режим Intent output в настройках сканера)
    "com.honeywell.decode.intent.action.EDIT_DATA" to listOf("data"),
    // Newland
    "nlscan.action.SCANNER_RESULT" to listOf("SCAN_BARCODE1"),
    // ATOL SMART.Slim (Android 7.0 / API 24)
    "com.xcheng.scanner.action.BARCODE_DECODING_BROADCAST" to
        listOf("EXTRA_BARCODE_DECODING_DATA"),
    // Симуляция в разработке
    "ru.wms.tsd.DEV_SCAN" to listOf("barcode"),
)

/**
 * Разбирает broadcast сканера без привязки к Android Intent, чтобы контракт
 * action/extra проверялся обычным JVM-тестом.
 */
internal fun parseHardwareBroadcast(
    action: String?,
    getExtra: (String) -> String?,
): ScanEvent? {
    val extraKeys = KNOWN_SCANNER_BROADCASTS[action] ?: return null
    val barcode = extraKeys.firstNotNullOfOrNull { key ->
        getExtra(key)?.takeIf { it.isNotBlank() }
    } ?: return null
    val source = if (action == "ru.wms.tsd.DEV_SCAN") {
        ScanSource.DEV
    } else {
        ScanSource.HARDWARE_BROADCAST
    }
    return ScanEvent(barcode, source)
}

/**
 * Ресивер аппаратных сканов. Регистрируется в MainActivity (onStart/onStop),
 * чтобы сканы принимались только когда приложение на экране.
 */
class HardwareScanReceiver(private val manager: ScannerManager) : BroadcastReceiver() {

    override fun onReceive(context: Context?, intent: Intent?) {
        val scan = parseHardwareBroadcast(intent?.action) { key ->
            intent?.getStringExtra(key)
        } ?: return
        manager.submit(scan.barcode, scan.source)
    }

    fun register(context: Context) {
        val filter = IntentFilter().apply {
            KNOWN_SCANNER_BROADCASTS.keys.forEach(::addAction)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.registerReceiver(this, filter, Context.RECEIVER_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            context.registerReceiver(this, filter)
        }
    }

    fun unregister(context: Context) {
        runCatching { context.unregisterReceiver(this) }
    }
}
