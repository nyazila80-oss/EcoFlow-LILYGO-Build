#!/usr/bin/env python3
Import('env')
from pathlib import Path

# 15J must instrument WiFiClientSecure before its translation unit is compiled.
# CI therefore resolves PlatformIO packages explicitly before the build starts.
# This script then patches the resolved framework immediately when SCons loads
# the pre: extra script.  Do not defer this to a firmware.elf pre-action: that
# action runs after ssl_client.cpp may already have been compiled.
def install_tls15j_framework_hook(env):
    package_dir = env.PioPlatform().get_package_dir('framework-arduinoespressif32')
    if not package_dir:
        raise RuntimeError(
            '15J: framework-arduinoespressif32 is not resolved; run '
            '`pio pkg install -e lilygo_tcan485` before building'
        )

    packages = Path(package_dir)
    base = packages / 'libraries' / 'WiFiClientSecure' / 'src'
    hdr = base / 'ssl_client.h'
    cpp = base / 'ssl_client.cpp'
    if not hdr.exists() or not cpp.exists():
        raise RuntimeError('15J: WiFiClientSecure framework sources not found')

    h = hdr.read_text(encoding='utf-8')
    s = cpp.read_text(encoding='utf-8')

    # Export only diagnostic getters. The capture itself lives in ssl_client.cpp so
    # it survives WiFiClientSecure::stop(), which clears the per-connection context.
    h_decl = '''\n// 15J diagnostic-only: X509 verification flags captured during handshake.\nuint32_t tls15j_get_verify_flags(void);\nint tls15j_get_verify_depth(void);\n'''
    if 'tls15j_get_verify_flags' not in h:
        anchor = 'bool get_peer_fingerprint(sslclient_context *ssl_client, uint8_t sha256[32]);\n'
        if anchor not in h:
            raise RuntimeError('15J: ssl_client.h declaration anchor missing')
        h = h.replace(anchor, anchor + h_decl, 1)

    capture = '''\n// 15J diagnostic-only capture. Returning 0 does NOT clear *flags, so normal\n// MBEDTLS_SSL_VERIFY_REQUIRED fail-closed validation remains authoritative.\nstatic volatile uint32_t s_tls15j_verify_flags = 0;\nstatic volatile int s_tls15j_verify_depth = -1;\nstatic int tls15j_verify_cb(void *, mbedtls_x509_crt *, int depth, uint32_t *flags)\n{\n    if (flags != NULL) s_tls15j_verify_flags |= *flags;\n    if (depth > s_tls15j_verify_depth) s_tls15j_verify_depth = depth;\n    return 0;\n}\nuint32_t tls15j_get_verify_flags(void) { return s_tls15j_verify_flags; }\nint tls15j_get_verify_depth(void) { return s_tls15j_verify_depth; }\n'''
    if 's_tls15j_verify_flags' not in s:
        anchor = 'const char *pers = "esp32-tls";\n'
        if anchor not in s:
            raise RuntimeError('15J: ssl_client.cpp global anchor missing')
        s = s.replace(anchor, anchor + capture, 1)

    reset_anchor = '    char buf[512];\n    int ret, flags;\n'
    reset = '    s_tls15j_verify_flags = 0;\n    s_tls15j_verify_depth = -1;\n'
    if reset not in s:
        if reset_anchor not in s:
            raise RuntimeError('15J: start_ssl_client reset anchor missing')
        s = s.replace(reset_anchor, reset_anchor + reset, 1)

    verify_anchor = '        mbedtls_ssl_conf_ca_chain(&ssl_client->ssl_conf, &ssl_client->ca_cert, NULL);\n'
    verify_line = '        mbedtls_ssl_conf_verify(&ssl_client->ssl_conf, tls15j_verify_cb, NULL);\n'
    if verify_line not in s:
        if verify_anchor not in s:
            raise RuntimeError('15J: CA-chain anchor missing')
        s = s.replace(verify_anchor, verify_anchor + verify_line, 1)

    # Safety invariants: observe verification only; never weaken it.
    for token in (
        'MBEDTLS_SSL_VERIFY_REQUIRED',
        'mbedtls_ssl_conf_verify(&ssl_client->ssl_conf, tls15j_verify_cb, NULL)',
        'return 0;',
    ):
        if token not in s:
            raise RuntimeError('15J invariant missing: ' + token)

    hdr.write_text(h, encoding='utf-8')
    cpp.write_text(s, encoding='utf-8')
    print('15J framework hook installed before compile: verify flags captured without changing fail-closed validation')

install_tls15j_framework_hook(env)
