package ru.wms.tsd.core.scanner

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.Executors
import kotlinx.coroutines.delay
import ru.wms.tsd.ui.theme.WmsColors
import ru.wms.tsd.ui.theme.WmsDimens

/**
 * P7 / T-03b. Полноэкранный сканер камерой (ML Kit) для обычных смартфонов.
 * Остаётся открытым для серийного сканирования: распознал → отдал в [onBarcode]
 * (обычно ScannerManager.submit) → зелёная рамка → пауза 2с от повторов.
 * Форматы: EAN/UPC/Code128/Code39 (ШК товаров и ячеек), QR, DataMatrix (коды ЧЗ).
 */
@Composable
fun CameraScannerSheet(
    onBarcode: (String) -> Unit,
    onClose: () -> Unit,
    /** Текст ошибки последнего скана (неверный ШК): показываем поверх превью. */
    scanErrorMessage: String? = null,
) {
    val context = LocalContext.current

    var hasPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    var permissionDenied by remember { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        hasPermission = granted
        permissionDenied = !granted
    }

    LaunchedEffect(Unit) {
        if (!hasPermission) permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    Dialog(
        onDismissRequest = onClose,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Box(modifier = Modifier.fillMaxSize().background(Color.Black)) {
            when {
                hasPermission -> CameraPreviewWithAnalyzer(onBarcode = onBarcode)
                permissionDenied -> Text(
                    "Нет доступа к камере.\nРазрешите камеру в настройках приложения",
                    color = Color.White,
                    fontSize = 18.sp,
                    modifier = Modifier.align(Alignment.Center).padding(32.dp),
                )
            }

            // Ошибка скана поверх превью — иначе она прячется на экране под шторкой
            if (scanErrorMessage != null) {
                Surface(
                    color = WmsColors.Error,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(16.dp)
                        .fillMaxWidth(),
                ) {
                    Text(
                        scanErrorMessage,
                        color = Color.White,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(20.dp),
                    )
                }
            }

            Button(
                onClick = onClose,
                colors = ButtonDefaults.buttonColors(containerColor = WmsColors.Surface),
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(24.dp)
                    .height(WmsDimens.PrimaryButtonHeight),
            ) {
                Text("Закрыть", fontSize = 20.sp, color = WmsColors.TextPrimary)
            }
        }
    }
}

@Composable
private fun CameraPreviewWithAnalyzer(onBarcode: (String) -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    // Пауза между сканами: серийное сканирование без дребезга одного и того же кода
    var lastScanAt by remember { mutableLongStateOf(0L) }
    var flashGreen by remember { mutableStateOf(false) }

    LaunchedEffect(flashGreen) {
        if (flashGreen) {
            delay(600)
            flashGreen = false
        }
    }

    val analyzerExecutor = remember { Executors.newSingleThreadExecutor() }
    val scanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(
                    Barcode.FORMAT_EAN_13,
                    Barcode.FORMAT_EAN_8,
                    Barcode.FORMAT_UPC_A,
                    Barcode.FORMAT_UPC_E,
                    Barcode.FORMAT_CODE_128,
                    Barcode.FORMAT_CODE_39,
                    Barcode.FORMAT_QR_CODE,
                    Barcode.FORMAT_DATA_MATRIX,
                )
                .build(),
        )
    }
    // Держим провайдер, чтобы снять привязку камеры при закрытии шторки.
    // Иначе камера остаётся привязанной к lifecycle активити (у Compose-Dialog
    // своего lifecycle нет) и продолжает работать в фоне — утечка железа камеры.
    val cameraProviderRef = remember { java.util.concurrent.atomic.AtomicReference<ProcessCameraProvider?>() }

    DisposableEffect(Unit) {
        onDispose {
            cameraProviderRef.getAndSet(null)?.unbindAll()
            analyzerExecutor.shutdown()
            scanner.close()
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                val previewView = PreviewView(ctx)
                val providerFuture = ProcessCameraProvider.getInstance(ctx)
                providerFuture.addListener({
                    val provider = providerFuture.get()
                    cameraProviderRef.set(provider)
                    val preview = Preview.Builder().build().also {
                        it.surfaceProvider = previewView.surfaceProvider
                    }
                    val analysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                    analysis.setAnalyzer(analyzerExecutor) { imageProxy ->
                        processFrame(scanner, imageProxy) { raw ->
                            val now = System.currentTimeMillis()
                            if (now - lastScanAt >= 2000) {
                                lastScanAt = now
                                flashGreen = true
                                onBarcode(raw)
                            }
                        }
                    }
                    provider.unbindAll()
                    provider.bindToLifecycle(
                        lifecycleOwner,
                        CameraSelector.DEFAULT_BACK_CAMERA,
                        preview,
                        analysis,
                    )
                }, ContextCompat.getMainExecutor(ctx))
                previewView
            },
        )

        // Рамка прицела; зеленеет на распознанный код
        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1.4f)
                    .border(
                        width = if (flashGreen) 6.dp else 3.dp,
                        color = if (flashGreen) WmsColors.Success else Color.White.copy(alpha = 0.8f),
                        shape = RoundedCornerShape(16.dp),
                    ),
            )
        }

        AnimatedVisibility(
            visible = flashGreen,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.fillMaxSize(),
        ) {
            Box(modifier = Modifier.fillMaxSize().background(WmsColors.Success.copy(alpha = 0.15f)))
        }

        Text(
            "Наведите камеру на штрихкод",
            color = Color.White,
            fontSize = 16.sp,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .padding(top = 48.dp),
        )
    }
}

@androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
private fun processFrame(
    scanner: com.google.mlkit.vision.barcode.BarcodeScanner,
    imageProxy: ImageProxy,
    onFound: (String) -> Unit,
) {
    val mediaImage = imageProxy.image
    if (mediaImage == null) {
        imageProxy.close()
        return
    }
    val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
    scanner.process(image)
        .addOnSuccessListener { barcodes ->
            barcodes.firstOrNull { !it.rawValue.isNullOrBlank() }?.rawValue?.let(onFound)
        }
        .addOnCompleteListener { imageProxy.close() }
}
