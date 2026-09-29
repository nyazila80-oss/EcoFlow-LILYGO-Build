# 9.36.7.13 TLS transport diagnostic

Purpose: isolate EcoFlow HTTPS failure `TLS -32512` after the BLE-off A/B test proved the failure persists with >34 kB largest8 before GET.

Changes:
- Removed the experimental `WiFiClientSecure::setBufferSizes()` call from 9.36.7.12 because it is not part of the pinned Arduino-ESP32 WiFiClientSecure API used by this project.
- Added DNS probe for `api-e.ecoflow.com`.
- Added a plain TCP connect probe to the resolved address on port 443. The probe sends no HTTP request, API key, secret, signature, or payload.
- Added INTERNAL|8BIT free/largest heap snapshots immediately before TLS object setup and after GET.
- Added job-status fields: `dns_ok`, `dns_ip_u32`, `tcp_443_ok`, `internal_free_pre`, `internal_largest_pre`, `internal_free_post`, `internal_largest_post`.
- Certificate verification remains enabled. Cloud writes remain blocked; GET-only behavior remains unchanged.

Host regression:
- `host_sim_v24_final_audit.py`: PASS (2,000,000 modeled operations, 0 violations).
- `host_sim_final_regression.py`: PASS (20 seeds; all reported reject/accept invariants completed).

Build status:
- Source patch is prepared and host regressions pass. A new ESP32 binary is not claimed here because PlatformIO Core is not present in the current Linux runtime. Existing `.pio` artifacts are from the preceding build and must not be relabeled as 9.36.7.13.
