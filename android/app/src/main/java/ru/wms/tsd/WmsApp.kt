package ru.wms.tsd

import android.app.Application
import android.content.Context

class WmsApp : Application() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base)
        CrashReportStore.install(this)
    }

    override fun onCreate() {
        super.onCreate()
        try {
            AppGraph.init(this)
        } catch (failure: Throwable) {
            // Не подменяем зашифрованное хранилище открытым. Сохраняем только
            // безопасный код/класс ошибки и даём MainActivity показать диагностику.
            CrashReportStore.recordInitFailure(this, failure)
        }
    }
}
