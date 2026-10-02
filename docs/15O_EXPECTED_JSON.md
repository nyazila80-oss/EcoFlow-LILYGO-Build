# 15O expected runtime JSON

`/api/powerstream/job` must retain the 15M chain and 15N verification detail and add `tls15o_version` plus `tls15o_cert_identity`.

Each `tls15o_cert_identity` entry is keyed by certificate depth and contains `serial`, `ski`, `aki`, `sig_oid_hex`, and `pk_raw_len`. Empty values are permitted for a depth that was not supplied to the verify callback.

The diagnostic is considered useful only when the hardware response can be correlated with the same connection attempt that produced the X.509 verification flags.
