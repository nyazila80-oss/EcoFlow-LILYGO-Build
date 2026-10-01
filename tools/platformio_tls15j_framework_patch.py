#!/usr/bin/env python3
Import('env')
from pathlib import Path

# PlatformIO runs pre: extra_scripts before the framework package is guaranteed
# to be installed/resolved on a clean runner. Resolve the configured framework
# package directory deterministically instead of failing on get_package_dir().
pkg = env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg:
    platform_dir = Path(env.PioPlatform().get_dir())
    candidates = [
        Path.home()/'.platformio'/'packages'/'framework-arduinoespressif32',
        platform_dir/'packages'/'framework-arduinoespressif32',
    ]
    pkg = next((str(p) for p in candidates if p.exists()), None)
if not pkg:
    # Do not weaken TLS or silently skip the patch. A clean runner must first
    # install the pinned framework package; fail closed with an actionable cause.
    raise RuntimeError('15J: framework package not installed before pre-script; install pinned framework before build')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
h_decl='''\nuint32_t tls15j_get_verify_flags(void);\nint tls15j_get_verify_depth(void);\n'''
if 'tls15j_get_verify_flags' not in h:
    a='bool get_peer_fingerprint(sslclient_context *ssl_client, uint8_t sha256[32]);\n'
    if a not in h: raise RuntimeError('15J header anchor missing')
    h=h.replace(a,a+h_decl,1)
capture='''\nstatic volatile uint32_t s_tls15j_verify_flags = 0;\nstatic volatile int s_tls15j_verify_depth = -1;\nstatic int tls15j_verify_cb(void *, mbedtls_x509_crt *, int depth, uint32_t *flags)\n{\n    if (flags != NULL) s_tls15j_verify_flags |= *flags;\n    if (depth > s_tls15j_verify_depth) s_tls15j_verify_depth = depth;\n    return 0;\n}\nuint32_t tls15j_get_verify_flags(void) { return s_tls15j_verify_flags; }\nint tls15j_get_verify_depth(void) { return s_tls15j_verify_depth; }\n'''
if 's_tls15j_verify_flags' not in s:
    a='const char *pers = "esp32-tls";\n'
    if a not in s: raise RuntimeError('15J global anchor missing')
    s=s.replace(a,a+capture,1)
a='    char buf[512];\n    int ret, flags;\n'; reset='    s_tls15j_verify_flags = 0;\n    s_tls15j_verify_depth = -1;\n'
if reset not in s:
    if a not in s: raise RuntimeError('15J reset anchor missing')
    s=s.replace(a,a+reset,1)
a='        mbedtls_ssl_conf_ca_chain(&ssl_client->ssl_conf, &ssl_client->ca_cert, NULL);\n'; v='        mbedtls_ssl_conf_verify(&ssl_client->ssl_conf, tls15j_verify_cb, NULL);\n'
if v not in s:
    if a not in s: raise RuntimeError('15J CA anchor missing')
    s=s.replace(a,a+v,1)
for t in ('MBEDTLS_SSL_VERIFY_REQUIRED','tls15j_verify_cb'):
    if t not in s: raise RuntimeError('15J safety invariant missing: '+t)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')
print('15J framework verify hook installed; VERIFY_REQUIRED retained')
