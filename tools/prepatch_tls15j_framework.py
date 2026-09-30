#!/usr/bin/env python3
"""15K CI prepatch: extend proven 15J verify callback with bounded chain metadata."""
from pathlib import Path
import os

root = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
base = root / "packages" / "framework-arduinoespressif32" / "libraries" / "WiFiClientSecure" / "src"
hdr = base / "ssl_client.h"
cpp = base / "ssl_client.cpp"
if not hdr.exists() or not cpp.exists():
    raise SystemExit(f"15K: WiFiClientSecure sources not found under {base}")
h = hdr.read_text(encoding="utf-8")
s = cpp.read_text(encoding="utf-8")

h_decl = '''\n// 15J/15K diagnostic-only TLS verification telemetry.\nuint32_t tls15j_get_verify_flags(void);\nint tls15j_get_verify_depth(void);\nuint32_t tls15k_get_chain_flags(int depth);\nconst char* tls15k_get_chain_subject(int depth);\nconst char* tls15k_get_chain_issuer(int depth);\nconst char* tls15k_get_chain_sha256(int depth);\n'''
if "tls15k_get_chain_sha256" not in h:
    anchor = "bool get_peer_fingerprint(sslclient_context *ssl_client, uint8_t sha256[32]);\n"
    if anchor not in h: raise SystemExit("15K: header anchor missing")
    # Remove old 15J declarations if present, then install combined declarations.
    h = h.replace("\n// 15J diagnostic-only: X509 verification flags captured during handshake.\nuint32_t tls15j_get_verify_flags(void);\nint tls15j_get_verify_depth(void);\n", "\n")
    h = h.replace(anchor, anchor + h_decl, 1)

old_start = s.find("// 15J diagnostic-only capture.")
old_end_token = "int tls15j_get_verify_depth(void) { return s_tls15j_verify_depth; }\n"
old_end = s.find(old_end_token)
if old_start >= 0 and old_end >= 0:
    s = s[:old_start] + s[old_end + len(old_end_token):]

capture = r'''// 15K diagnostic-only bounded chain capture. Never changes *flags.
static volatile uint32_t s_tls15j_verify_flags = 0;
static volatile int s_tls15j_verify_depth = -1;
static uint32_t s_tls15k_flags[4] = {0,0,0,0};
static char s_tls15k_subject[4][192] = {{0}};
static char s_tls15k_issuer[4][192] = {{0}};
static char s_tls15k_sha256[4][65] = {{0}};
static void tls15k_hex(const unsigned char *in, size_t n, char *out) {
    static const char h[]="0123456789abcdef";
    for(size_t i=0;i<n;i++){ out[i*2]=h[in[i]>>4]; out[i*2+1]=h[in[i]&15]; }
    out[n*2]=0;
}
static int tls15j_verify_cb(void *, mbedtls_x509_crt *crt, int depth, uint32_t *flags)
{
    if (flags != NULL) s_tls15j_verify_flags |= *flags;
    if (depth > s_tls15j_verify_depth) s_tls15j_verify_depth = depth;
    if (crt != NULL && depth >= 0 && depth < 4) {
        s_tls15k_flags[depth] = flags ? *flags : 0;
        mbedtls_x509_dn_gets(s_tls15k_subject[depth], sizeof(s_tls15k_subject[depth]), &crt->subject);
        mbedtls_x509_dn_gets(s_tls15k_issuer[depth], sizeof(s_tls15k_issuer[depth]), &crt->issuer);
        unsigned char digest[32];
        if (mbedtls_sha256_ret(crt->raw.p, crt->raw.len, digest, 0) == 0)
            tls15k_hex(digest, sizeof(digest), s_tls15k_sha256[depth]);
    }
    return 0;
}
uint32_t tls15j_get_verify_flags(void) { return s_tls15j_verify_flags; }
int tls15j_get_verify_depth(void) { return s_tls15j_verify_depth; }
uint32_t tls15k_get_chain_flags(int d) { return (d>=0&&d<4)?s_tls15k_flags[d]:0; }
const char* tls15k_get_chain_subject(int d) { return (d>=0&&d<4)?s_tls15k_subject[d]:""; }
const char* tls15k_get_chain_issuer(int d) { return (d>=0&&d<4)?s_tls15k_issuer[d]:""; }
const char* tls15k_get_chain_sha256(int d) { return (d>=0&&d<4)?s_tls15k_sha256[d]:""; }
'''
anchor = 'const char *pers = "esp32-tls";\n'
if "tls15k_get_chain_sha256" not in s:
    if anchor not in s: raise SystemExit("15K: cpp global anchor missing")
    s = s.replace(anchor, anchor + capture, 1)

reset_anchor = "    char buf[512];\n    int ret, flags;\n"
reset = "    s_tls15j_verify_flags = 0;\n    s_tls15j_verify_depth = -1;\n    memset(s_tls15k_flags,0,sizeof(s_tls15k_flags));\n    memset(s_tls15k_subject,0,sizeof(s_tls15k_subject));\n    memset(s_tls15k_issuer,0,sizeof(s_tls15k_issuer));\n    memset(s_tls15k_sha256,0,sizeof(s_tls15k_sha256));\n"
# Replace 15J reset with 15K reset.
s = s.replace("    s_tls15j_verify_flags = 0;\n    s_tls15j_verify_depth = -1;\n", reset, 1)
if reset not in s:
    if reset_anchor not in s: raise SystemExit("15K: reset anchor missing")
    s = s.replace(reset_anchor, reset_anchor + reset, 1)

verify_anchor = "        mbedtls_ssl_conf_ca_chain(&ssl_client->ssl_conf, &ssl_client->ca_cert, NULL);\n"
verify_line = "        mbedtls_ssl_conf_verify(&ssl_client->ssl_conf, tls15j_verify_cb, NULL);\n"
if verify_line not in s:
    if verify_anchor not in s: raise SystemExit("15K: verify anchor missing")
    s = s.replace(verify_anchor, verify_anchor + verify_line, 1)
if '#include "mbedtls/sha256.h"' not in s:
    inc_anchor = '#include "ssl_client.h"\n'
    if inc_anchor not in s: raise SystemExit("15K: include anchor missing")
    s = s.replace(inc_anchor, inc_anchor + '#include "mbedtls/sha256.h"\n', 1)
for token in ("MBEDTLS_SSL_VERIFY_REQUIRED", "tls15k_get_chain_sha256", "return 0;"):
    if token not in s: raise SystemExit("15K invariant missing: "+token)
hdr.write_text(h, encoding="utf-8")
cpp.write_text(s, encoding="utf-8")
print("15K PREPATCH PASS: bounded subject/issuer/SHA256 capture; fail-closed verification unchanged")
