package ru.wms.tsd.ui.patterns

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import ru.wms.tsd.AppGraph
import ru.wms.tsd.core.scanner.CameraScannerSheet
import ru.wms.tsd.core.scanner.ScanSource
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * Результат последнего скана для визуального/звукового фидбэка.
 * Экран меняет значение — ScanScaffold сам показывает вспышку, играет звук,
 * вибрирует и гасит состояние через ~3 секунды.
 */
sealed interface ScanFlash {
    data object None : ScanFlash
    data class Success(val stamp: Long) : ScanFlash
    data class Error(val message: String, val stamp: Long) : ScanFlash
}

/**
 * P1. Каркас рабочего экрана ТСД (02_UX_SPEC.md §P1):
 * шапка (выход + название + прогресс X из Y), контент, нижняя основная кнопка,
 * вспышки успеха/ошибки поверх всего.
 */
@Composable
fun ScanScaffold(
    title: String,
    flash: ScanFlash,
    onExit: () -> Unit,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    progressDone: Int? = null,
    progressTotal: Int? = null,
    primaryActionLabel: String? = null,
    primaryActionEnabled: Boolean = true,
    onPrimaryAction: () -> Unit = {},
    /** Кнопка камеры-сканера в шапке (T-03b). Выключить на экранах без сканов. */
    cameraScanner: Boolean = true,
    content: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val feedback = remember { ScanFeedback(context) }
    var visibleFlash by remember { mutableStateOf<ScanFlash>(ScanFlash.None) }
    var showCamera by remember { mutableStateOf(false) }

    LaunchedEffect(flash) {
        visibleFlash = flash
        when (flash) {
            is ScanFlash.Success -> feedback.success()
            is ScanFlash.Error -> feedback.error()
            ScanFlash.None -> return@LaunchedEffect
        }
        delay(if (flash is ScanFlash.Error) 3500 else 700)
        visibleFlash = ScanFlash.None
    }

    Box(modifier = modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().background(WmsColors.Background)) {
            Surface(color = WmsColors.Surface, shadowElevation = 2.dp) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = onExit, modifier = Modifier.padding(4.dp)) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                        }
                        Column(modifier = Modifier.weight(1f).padding(vertical = 8.dp)) {
                            Text(title, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                            if (subtitle != null) {
                                Text(subtitle, fontSize = 14.sp, color = WmsColors.TextSecondary, maxLines = 1)
                            }
                        }
                        if (progressDone != null && progressTotal != null) {
                            Text(
                                "$progressDone из $progressTotal",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = WmsColors.Primary,
                                modifier = Modifier.padding(end = 4.dp),
                            )
                        }
                        if (cameraScanner) {
                            IconButton(onClick = { showCamera = true }, modifier = Modifier.padding(end = 4.dp)) {
                                Icon(
                                    Icons.Default.QrCodeScanner,
                                    contentDescription = "Сканировать камерой",
                                    tint = WmsColors.Primary,
                                )
                            }
                        }
                    }
                    if (progressDone != null && progressTotal != null && progressTotal > 0) {
                        LinearProgressIndicator(
                            progress = { progressDone.toFloat() / progressTotal },
                            modifier = Modifier.fillMaxWidth().height(6.dp),
                            color = WmsColors.Primary,
                        )
                    }
                }
            }

            Box(modifier = Modifier.weight(1f)) { content() }

            if (primaryActionLabel != null) {
                Button(
                    onClick = onPrimaryAction,
                    enabled = primaryActionEnabled,
                    colors = ButtonDefaults.buttonColors(containerColor = WmsColors.Primary),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                        .height(WmsDimens.PrimaryButtonHeight),
                ) {
                    Text(primaryActionLabel, fontSize = 20.sp)
                }
            }
        }

        if (showCamera) {
            CameraScannerSheet(
                // Прокидываем текст ошибки скана (неверный ШК) — показываем его ВНУТРИ
                // шторки камеры, иначе вспышка экрана прячется под ней и пользователь
                // думает, что скан прошёл. Звук/вибрация ошибки уже сработали выше.
                scanErrorMessage = (visibleFlash as? ScanFlash.Error)?.message,
                onBarcode = { AppGraph.scannerManager.submit(it, ScanSource.CAMERA) },
                onClose = { showCamera = false },
            )
        }

        // Вспышка результата скана поверх всего экрана
        AnimatedVisibility(
            visible = visibleFlash !is ScanFlash.None,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.fillMaxSize(),
        ) {
            val isError = visibleFlash is ScanFlash.Error
            val color = if (isError) WmsColors.Error else WmsColors.Success
            Box(modifier = Modifier.fillMaxSize().background(color.copy(alpha = 0.18f))) {
                if (isError) {
                    Surface(
                        color = WmsColors.Error,
                        shape = MaterialTheme.shapes.medium,
                        modifier = Modifier
                            .align(Alignment.TopCenter)
                            .padding(16.dp)
                            .fillMaxWidth(),
                    ) {
                        Text(
                            (visibleFlash as ScanFlash.Error).message,
                            color = WmsColors.Surface,
                            fontSize = 20.sp,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(20.dp),
                        )
                    }
                }
            }
        }
    }
}
