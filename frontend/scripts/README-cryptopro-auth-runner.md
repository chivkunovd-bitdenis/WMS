# WMS-517 independent auth and document CAdES runner

`verify-cryptopro-auth-cades.mjs` is an independent cryptographic check for the True API
browser-auth and withdrawal-document profiles. It does not call the CryptoPro browser
mock, True API, or any certificate/key cabinet.

The runner:

1. pins a JavaScript challenge containing Cyrillic, a non-breaking space, CRLF, Greek,
   and a surrogate pair to an explicit UCS-2LE byte fixture without a BOM;
2. creates a one-day ephemeral RSA test key and certificate in an OS temporary directory;
3. creates an attached CMS SignedData with the OpenSSL 3 `-cades` option, which includes
   the SigningCertificateV2 attribute required for the tested CAdES-BES profile;
4. independently verifies the CAdES signature and certificate binding, extracts the
   embedded content, and compares it byte-for-byte with the pinned UCS-2LE fixture;
5. changes one embedded content byte and requires verification to fail;
6. reads the same exact `LK_RECEIPT`-shaped UTF-8/base64/SHA-256 fixture used by
   `CryptoProCadesAdapter.signDetachedDocument`'s fake-adapter test;
7. creates a detached CAdES-BES CMS, verifies it independently against those exact
   decoded bytes, and requires verification to fail after a one-byte payload change;
8. deletes the temporary key, certificate, CMS, and content files in `finally`.

Run from `frontend`:

```sh
npm run test:crypto-auth
```

The runner requires OpenSSL 3 with `openssl cms -cades`. It automatically uses the
Homebrew OpenSSL 3 path on macOS or `openssl` on the Ubuntu CI runner. Another compatible
binary can be selected with `OPENSSL_BIN=/absolute/path/to/openssl`.

This is real CMS/CAdES verification with a disposable software certificate. It proves
the attached/default-UCS-2LE auth profile and the exact-UTF-8/base64/detached document
profile independently from the browser fake. The shared fixture connects the runner to
the actual adapter rule `ContentEncoding=BASE64_TO_BINARY`, unchanged `payload_base64`,
and `SignCades(..., CAdES-BES, true)`; the runner never parses or reserializes the bytes
before signing. It does not prove GOST provider behavior, CryptoPro CSP/native-host
readiness, a physical USB token, its PIN/user-presence flow, or True API sandbox
acceptance. Those remain separate BR17/B2 acceptance layers.
