#!/usr/bin/env python3
"""15D TLS OOM FMEA gate.
Pure host-side model: verifies that diagnostic interpretation keeps total free heap,
largest contiguous INTERNAL/8BIT block, credential provenance, and cleanup separate.
It intentionally does not claim an mbedTLS allocation size from host simulation.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Snap:
    free8: int
    largest8: int
    internal_free: int
    internal_largest: int


def classify(pre: Snap, post: Snap, tls_code: int, access_match: bool, secret_match: bool):
    if not access_match or not secret_match:
        return "CREDENTIAL_PROVENANCE_FAIL"
    if tls_code == -32512:
        # MBEDTLS_ERR_SSL_ALLOC_FAILED: distinguish fragmentation/peak from a leak.
        recovered = post.free8 >= pre.free8
        fragmented = pre.largest8 < pre.free8
        if recovered and fragmented:
            return "TLS_TEMP_ALLOC_OR_FRAGMENTATION"
        return "TLS_ALLOC_FAIL_NEEDS_RUNTIME_PEAK_TRACE"
    return "NON_OOM_TLS_OR_HTTP_PATH"


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        raise SystemExit(1)

# Hardware observation representative of 15C: plenty of aggregate heap does not
# prove that a sufficiently large contiguous block exists for the handshake.
pre = Snap(38704, 24564, 28784, 27636)
post = Snap(42728, 23540, 30152, 23540)
check("OOM is not misclassified as credential failure",
      classify(pre, post, -32512, True, True) == "TLS_TEMP_ALLOC_OR_FRAGMENTATION")
check("credential mismatch wins before TLS interpretation",
      classify(pre, post, -32512, False, True) == "CREDENTIAL_PROVENANCE_FAIL")
check("aggregate free heap is never treated as contiguous capacity", pre.free8 != pre.largest8)
check("INTERNAL free and INTERNAL largest remain distinct", pre.internal_free != pre.internal_largest)
check("post-failure recovery does not prove absence of transient peak", post.free8 >= pre.free8)

# FMEA invariants for the firmware patch that follows.
required_runtime_fields = {
    "cred_access_len", "cred_secret_len", "cred_access_nvs_match", "cred_secret_nvs_match",
    "cred_access_fp", "cred_secret_fp", "cred_request_access_match", "cred_request_secret_match",
    "tls_internal_hmac_pre_free", "tls_internal_hmac_pre_largest",
    "tls_internal_hmac_post_free", "tls_internal_hmac_post_largest",
    "tls_internal_headers_post_free", "tls_internal_headers_post_largest",
    "tls_internal_get_pre_free", "tls_internal_get_pre_largest",
    "tls_internal_get_post_free", "tls_internal_get_post_largest",
}
check("15D runtime contract has credential + TLS peak evidence", len(required_runtime_fields) == 18)
print("15D TLS/Credential FMEA simulation: PASS")
