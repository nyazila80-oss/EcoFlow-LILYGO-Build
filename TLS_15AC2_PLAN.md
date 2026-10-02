# 9.36.7.15AC2 — Stock TLS/X.509 comparison

Parent: 15AB hardware baseline.

Goal: explain TLS/X.509 `-9984` observed with ~42,996 B largest8, without changing BLE auth or memory lifecycle.

## Isolation
- Keep certificate verification enabled. Never use `setInsecure()` or VERIFY_NONE.
- Preserve endpoint, request headers, credentials handling, Wi-Fi path and CA material for the first A/B comparison.
- Compare stock mbedTLS/Arduino TLS verification path against the diagnostic 15P/15Q/15R/15X/15Y hot-path instrumentation.
- Do not change PowerStream BLE auth in this branch.

## A/B
A: current 15AB TLS path and existing telemetry.
B: same request/CA/time/endpoint but remove/bypass only active crypto hot-path probes that can alter verification execution; retain passive pre/post memory and error telemetry.

If B succeeds, instrumentation is causal until disproven. If B still returns -9984, next gate is CA/chain/time verification with exact verify flags and peer-chain metadata, never certificate contents/secrets.

## Required telemetry
- sane epoch immediately pre-handshake
- free/largest8 pre/post
- TLS native return code + symbolic error
- X.509 verify flags when obtainable without altering verification
- peer chain count and public metadata only (key type/bits, validity result), no raw cert dump
- CA parse result/count

## Acceptance
No TLS fix is accepted until certificate verification remains enabled and >=3 cold-boot hardware requests pass with the same endpoint and credentials.