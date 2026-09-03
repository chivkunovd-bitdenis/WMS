package ru.wms.tsd.core.scanner

enum class ScanSource {
    /** Аппаратный сканер ТСД, отдающий broadcast-интенты (Urovo/Zebra/Chainway/Honeywell). */
    HARDWARE_BROADCAST,

    /** Аппаратный сканер в режиме эмуляции клавиатуры (keyboard wedge). */
    KEYBOARD_WEDGE,

    /** Камера смартфона (ML Kit), тикет T-03b. */
    CAMERA,

    /** Симуляция скана в разработке: adb shell am broadcast -a ru.wms.tsd.DEV_SCAN --es barcode "..." */
    DEV,
}

data class ScanEvent(
    val barcode: String,
    val source: ScanSource,
)
