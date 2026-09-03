package ru.wms.tsd

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Process
import android.os.SystemClock
import android.view.KeyEvent
import android.view.ViewGroup
import android.annotation.SuppressLint
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import ru.wms.tsd.core.scanner.HardwareScanReceiver
import ru.wms.tsd.core.scanner.WedgeKeyAccumulator
import ru.wms.tsd.features.auth.LoginScreen
import ru.wms.tsd.ui.theme.WmsTheme

class MainActivity : ComponentActivity() {

    private val scanReceiver = HardwareScanReceiver(AppGraph.scannerManager)
    private val wedge = WedgeKeyAccumulator(AppGraph.scannerManager)
    private var diagnosticMode = false
    private var scanReceiverRegistered = false

    override fun onStart() {
        super.onStart()
        // Диагностический экран должен остаться доступным, даже если сбой вызван
        // vendor-реализацией broadcast-сканера на конкретном ТСД.
        if (!diagnosticMode) {
            scanReceiver.register(this)
            scanReceiverRegistered = true
        }
    }

    override fun onStop() {
        if (scanReceiverRegistered) {
            scanReceiver.unregister(this)
            scanReceiverRegistered = false
        }
        super.onStop()
    }

    // ComponentActivity marks this override restricted, but pre-dispatch is required
    // because a focused Compose TextField may consume key events before onKeyDown/onKeyUp.
    @SuppressLint("RestrictedApi")
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (!diagnosticMode && wedge.feed(event)) return true
        return super.dispatchKeyEvent(event)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        CrashReportStore.read(this)?.let { safeReport ->
            diagnosticMode = true
            showDiagnosticScreen(safeReport)
            return
        }

        setContent {
            WmsTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    MainContent()
                }
            }
        }
    }

    private fun showDiagnosticScreen(safeReport: String) {
        val padding = (20 * resources.displayMetrics.density).toInt()
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
        }
        content.addView(TextView(this).apply {
            text = "Диагностика WMS ТСД"
            textSize = 24f
        })
        content.addView(TextView(this).apply {
            text = "Приложение сохранило безопасный технический код последнего сбоя. " +
                "В отчёте нет паролей, PIN-кодов, токенов, адресов сервера или данных сотрудников."
            textSize = 16f
            setPadding(0, padding / 2, 0, padding / 2)
        })
        content.addView(TextView(this).apply {
            text = safeReport
            textSize = 14f
            setTextIsSelectable(true)
        })
        content.addView(Button(this).apply {
            text = "Скопировать безопасный отчёт"
            setOnClickListener {
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                clipboard.setPrimaryClip(android.content.ClipData.newPlainText("WMS TSD diagnostics", safeReport))
                Toast.makeText(this@MainActivity, "Отчёт скопирован", Toast.LENGTH_SHORT).show()
            }
        })
        content.addView(Button(this).apply {
            text = "Очистить отчёт и перезапустить"
            setOnClickListener { restartAfterClearingReport() }
        })
        setContentView(ScrollView(this).apply {
            addView(
                content,
                ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
        })
    }

    private fun restartAfterClearingReport() {
        CrashReportStore.clear(this)
        val restartIntent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            1701,
            restartIntent,
            PendingIntent.FLAG_CANCEL_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val alarmManager = getSystemService(Context.ALARM_SERVICE) as AlarmManager
        @Suppress("DEPRECATION")
        alarmManager.set(
            AlarmManager.ELAPSED_REALTIME,
            SystemClock.elapsedRealtime() + 300,
            pendingIntent,
        )
        Process.killProcess(Process.myPid())
    }
}

@Composable
private fun MainContent() {
    val authManager = AppGraph.getAuthManager()
    val authStore = AppGraph.getAuthStore()
    var isLoggedIn by remember { mutableStateOf(authManager.isLoggedIn()) }

    // 401 от API: токен протух — возвращаем на экран входа (T-05c)
    androidx.compose.runtime.LaunchedEffect(Unit) {
        authManager.sessionExpired.collect { isLoggedIn = false }
    }

    if (isLoggedIn && authManager.getCurrentSession() != null) {
        val session = authManager.getCurrentSession()!!
        AppNavHost(
            session = session,
            onLogout = {
                authManager.logout()
                isLoggedIn = false
            }
        )
    } else {
        LoginScreen(
            authStore = authStore,
            authManager = authManager,
            onLoginSuccess = {
                isLoggedIn = true
            }
        )
    }
}
