package ru.wms.tsd.core.api

import java.io.File
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Base64

/**
 * SHA-256 отпечаток ISRG Root X1 с https://letsencrypt.org/certs/isrgrootx1.pem
 * 96:BC:EC:06:26:49:76:F3:74:60:77:9A:CF:28:C5:A7:CF:E8:A3:C0:AA:E1:1A:8F:FC:EE:05:C0:BD:DF:08:C6
 */
internal const val ISRG_ROOT_X1_SHA256 =
    "96BCEC06264976F37460779ACF28C5A7CFE8A3C0AAE11A8FFCEE05C0BDDF08C6"

internal fun sha256FingerprintOfPem(pemText: String): String {
    val base64 = pemText
        .replace("-----BEGIN CERTIFICATE-----", "")
        .replace("-----END CERTIFICATE-----", "")
        .replace("\\s".toRegex(), "")
    val digest = MessageDigest.getInstance("SHA-256")
        .digest(Base64.getDecoder().decode(base64))
    return digest.joinToString("") { "%02X".format(it) }
}

internal fun verifyIsrgRootX1Pem(pemText: String): Boolean {
    if (sha256FingerprintOfPem(pemText) != ISRG_ROOT_X1_SHA256) return false
    val cert = CertificateFactory.getInstance("X.509")
        .generateCertificate(pemText.byteInputStream()) as X509Certificate
    return cert.subjectX500Principal.name.contains("ISRG Root X1")
}

internal fun defaultIsrgRootPemFile(): File {
    val candidates = listOf(
        File("src/main/res/raw/isrgrootx1.pem"),
        File("app/src/main/res/raw/isrgrootx1.pem"),
    )
    return candidates.firstOrNull { it.isFile }
        ?: error("ISRG Root X1 PEM resource missing")
}
