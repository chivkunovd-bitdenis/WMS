package ru.wms.tsd.core.auth

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString

/**
 * Модель сохранённого сотрудника на устройстве.
 */
@Serializable
data class SavedStaff(
    val email: String,
    val displayName: String,
    val token: String,
    val pin: String, // 4 цифры
)

/**
 * Хранилище авторизации на устройстве через EncryptedSharedPreferences.
 * Сохраняет: base URL сервера, список сохранённых сотрудников.
 */
class AuthStore(context: Context) {
    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val encryptedPrefs = EncryptedSharedPreferences.create(
        context,
        PREFS_FILE_NAME,
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    private val json = Json { ignoreUnknownKeys = true }

    fun getBaseUrl(): String? = encryptedPrefs.getString(KEY_BASE_URL, null)

    fun setBaseUrl(url: String) {
        encryptedPrefs.edit().putString(KEY_BASE_URL, url).apply()
    }

    fun getSavedStaff(): List<SavedStaff> {
        val jsonStr = encryptedPrefs.getString(KEY_SAVED_STAFF, null) ?: return emptyList()
        return try {
            json.decodeFromString(jsonStr)
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun saveStaff(staff: SavedStaff) {
        val current = getSavedStaff().toMutableList()
        current.removeAll { it.email == staff.email }
        current.add(staff)
        val jsonStr = json.encodeToString(current)
        encryptedPrefs.edit().putString(KEY_SAVED_STAFF, jsonStr).apply()
    }

    /** Токен умер (401): PIN-плитка остаётся, но вход по ней потребует пароль. */
    fun invalidateToken(email: String) {
        val staff = getSavedStaff().find { it.email == email } ?: return
        saveStaff(staff.copy(token = ""))
    }

    fun removeStaff(email: String) {
        val current = getSavedStaff().toMutableList()
        current.removeAll { it.email == email }
        val jsonStr = json.encodeToString(current)
        encryptedPrefs.edit().putString(KEY_SAVED_STAFF, jsonStr).apply()
    }

    fun clear() {
        encryptedPrefs.edit().clear().apply()
    }

    companion object {
        internal const val PREFS_FILE_NAME = "auth_store"
        internal const val KEY_BASE_URL = "base_url"
        internal const val KEY_SAVED_STAFF = "saved_staff"
    }
}
