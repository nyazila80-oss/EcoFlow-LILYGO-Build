# 15O diagnostic scope

Baseline: hardware-tested 15N.

15O adds observation-only certificate identity telemetry: serial, Subject Key Identifier, Authority Key Identifier, signature OID bytes, and public-key DER length for each certificate seen by the verify callback.

Safety invariants: certificate verification remains required; the existing EcoFlow CA bundle is unchanged; no insecure TLS mode is introduced; 15L remains frozen and is not merged into this diagnostic branch.

The purpose is to determine whether the received leaf and intermediate certificates form the expected key-identifier relationship before any trust-store change is considered.
