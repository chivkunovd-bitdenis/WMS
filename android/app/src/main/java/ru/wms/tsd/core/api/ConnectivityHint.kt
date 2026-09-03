package ru.wms.tsd.core.api

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/**
 * Ранний UX-хинт по наличию сети. Решающим остаётся фактический HTTP-запрос.
 */
class ConnectivityHint(context: Context) {
    private val connectivityManager =
        context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    fun hasActiveNetwork(): Boolean {
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}

fun isConnectivityClassFailure(failure: NetworkFailure): Boolean = when (failure) {
    NetworkFailure.DnsFailure,
    NetworkFailure.ConnectionRefused,
    NetworkFailure.Timeout -> true
    else -> false
}

/**
 * Уточняет результат только после сетевого сбоя: при отсутствии сети по хинту
 * connectivity-класс ошибок становится [NetworkFailure.NoActiveNetwork].
 */
fun refineWithConnectivityHint(
    failure: NetworkFailure,
    hasActiveNetwork: Boolean,
): NetworkFailure {
    if (hasActiveNetwork || !isConnectivityClassFailure(failure)) {
        return failure
    }
    return NetworkFailure.NoActiveNetwork
}
