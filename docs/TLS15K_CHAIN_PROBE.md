# 9.36.7.15K X509 Chain Probe

Purpose: identify the exact certificate at the failing X509 depth observed by 15J.

Hardware evidence from 15J:
- TLS error: -9984 / X509 certificate verification failed
- verify flags: 0x00000008
- MBEDTLS_X509_BADCERT_NOT_TRUSTED: true
- failing/highest observed depth: 2
- CA verification enabled

15K requirements:
1. Keep MBEDTLS_SSL_VERIFY_REQUIRED and the existing CA verification enabled.
2. Never call setInsecure().
3. Observe, but never clear or modify, mbedTLS verify flags.
4. Capture up to four certificate depths during the verify callback.
5. For each depth capture only non-secret certificate metadata: depth, raw flags, subject DN, issuer DN, SHA-256 fingerprint of the DER certificate.
6. Do not expose EcoFlow AccessKey, SecretKey, HMAC material, request headers, or payloads.
7. Keep Cloud writes disabled; this remains a diagnostic GET-only build.
8. Build must pass Full Clean, USB/OTA firmware, filesystem and binary provenance gates before hardware use.

Decision gate after hardware test:
- Compare depth 0..N subject/issuer/fingerprint with the configured trust anchor.
- Only after this evidence may the trust store be changed.
- A later CA fix must remain fail-closed; no insecure fallback is permitted.
