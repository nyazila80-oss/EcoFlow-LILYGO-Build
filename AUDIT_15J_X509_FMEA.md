# 9.36.7.15J — X509 diagnostic FMEA

Hardware baseline (15I): TLS failed with mbedTLS -9984 / -0x2700 while CA verification was enabled, time was sane, NimBLE was disabled, and pre/post verify INTERNAL largest block was about 47 kB. A transient 4-byte INTERNAL allocation failure was also observed and remains a separate signal.

## 15J questions

1. Is the expected trust anchor still compiled into the actual firmware?
2. Is the embedded PEM present at runtime with a non-zero deterministic byte count?
3. Does the raw TLS error remain -9984 with the same isolated BLE-off baseline?
4. Does the transient allocation failure recur at the same time?

## Safety invariants

- CA verification remains enabled through `client.setCACert(ECOFLOW_CA_BUNDLE)`.
- No executable `setInsecure()` is permitted.
- 15J does not change AccessKey/SecretKey handling or cloud write policy.
- 15J does not claim peer verify flags that the public Arduino WiFiClientSecure API does not expose.

## Hardware gate

Run exactly one read-only EcoFlow cloud request with BLE startup disabled. Capture the full PowerStream cloud diagnostic JSON. Compare `tls15i_last_error`, `tls15i_x509_verify_failed`, `tls15j_trust_anchor`, `tls15j_ca_pem_bytes`, epoch/time sanity, INTERNAL pre/post verify, and failed-allocation snapshot against 15I.
