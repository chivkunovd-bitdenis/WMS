package ru.wms.tsd.ui.patterns

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.annotation.RequiresApi

/**
 * Звук + вибрация по результату скана (правило 3 из 02_UX_SPEC.md).
 * Успех — короткий бип и короткая вибрация; ошибка — низкий тон и длинная вибрация,
 * различимые не глядя на экран.
 */
class ScanFeedback(context: Context) {

    private val vibrator: Vibrator? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }

    private val tones = runCatching { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 90) }.getOrNull()

    fun success() {
        tones?.startTone(ToneGenerator.TONE_PROP_BEEP, 120)
        vibrate(60)
    }

    fun error() {
        tones?.startTone(ToneGenerator.TONE_SUP_ERROR, 350)
        vibrate(400)
    }

    private fun vibrate(ms: Long) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrateWithEffect(ms)
        } else {
            @Suppress("DEPRECATION")
            vibrator?.vibrate(ms)
        }
    }

    @RequiresApi(Build.VERSION_CODES.O)
    private fun vibrateWithEffect(ms: Long) {
        vibrator?.vibrate(
            VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE),
        )
    }
}

internal enum class VibrationMode {
    EFFECT,
    LEGACY,
}

/** Android 7 (API 24) не содержит VibrationEffect, появившийся только в API 26. */
internal fun vibrationModeForSdk(sdkInt: Int): VibrationMode =
    if (sdkInt >= Build.VERSION_CODES.O) VibrationMode.EFFECT else VibrationMode.LEGACY
