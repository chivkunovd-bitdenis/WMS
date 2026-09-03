package ru.wms.tsd.core.scanner

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * Единая точка входа для всех источников сканов. Экраны подписываются на [scans]
 * и не знают, откуда пришёл штрихкод — ТСД, wedge, камера или dev-симуляция.
 *
 * Экран, готовый принимать сканы, собирает flow через collectAsStateWithLifecycle /
 * LaunchedEffect; если экран не подписан — скан просто теряется (extraBufferCapacity
 * не копит очередь: сканировать «в никуда» на складе = ошибка, а не отложенный ввод).
 */
class ScannerManager {
    private val _scans = MutableSharedFlow<ScanEvent>(extraBufferCapacity = 1)
    val scans: SharedFlow<ScanEvent> = _scans

    fun submit(rawBarcode: String, source: ScanSource) {
        val barcode = rawBarcode.trim()
        if (barcode.isEmpty()) return
        _scans.tryEmit(ScanEvent(barcode, source))
    }
}
