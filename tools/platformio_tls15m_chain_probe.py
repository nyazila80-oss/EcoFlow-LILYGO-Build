#!/usr/bin/env python3
Import('env')
from pathlib import Path

pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15M: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'
hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for token in ('tls15j_get_verify_flags','tls15j_verify_cb','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if token not in h+s: raise RuntimeError('15M requires 15J framework hook: '+token)

decl='''\n// 15M diagnostic-only certificate-chain telemetry.\nuint32_t tls15m_get_depth_flags(int depth);\nconst char* tls15m_get_subject(int depth);\nconst char* tls15m_get_issuer(int depth);\n'''
if 'tls15m_get_depth_flags' not in h: h += decl

storage='''\n#define TLS15M_MAX_DEPTH 4\nstatic volatile uint32_t s_tls15m_depth_flags[TLS15M_MAX_DEPTH] = {0};\nstatic char s_tls15m_subject[TLS15M_MAX_DEPTH][192] = {{0}};\nstatic char s_tls15m_issuer[TLS15M_MAX_DEPTH][192] = {{0}};\nuint32_t tls15m_get_depth_flags(int d){ return (d>=0 && d<TLS15M_MAX_DEPTH)?s_tls15m_depth_flags[d]:0; }\nconst char* tls15m_get_subject(int d){ return (d>=0 && d<TLS15M_MAX_DEPTH)?s_tls15m_subject[d]:""; }\nconst char* tls15m_get_issuer(int d){ return (d>=0 && d<TLS15M_MAX_DEPTH)?s_tls15m_issuer[d]:""; }\n'''
anchor='static volatile int s_tls15j_verify_depth = -1;\n'
if 's_tls15m_depth_flags' not in s:
    if anchor not in s: raise RuntimeError('15M: 15J storage anchor missing')
    s=s.replace(anchor,anchor+storage,1)
old='static int tls15j_verify_cb(void *, mbedtls_x509_crt *, int depth, uint32_t *flags)\n{\n    if (flags != NULL) s_tls15j_verify_flags |= *flags;\n    if (depth > s_tls15j_verify_depth) s_tls15j_verify_depth = depth;\n    return 0;\n}'
new='''static int tls15j_verify_cb(void *, mbedtls_x509_crt *crt, int depth, uint32_t *flags)\n{\n    if (flags != NULL) s_tls15j_verify_flags |= *flags;\n    if (depth > s_tls15j_verify_depth) s_tls15j_verify_depth = depth;\n    if (depth >= 0 && depth < TLS15M_MAX_DEPTH) {\n        if (flags != NULL) s_tls15m_depth_flags[depth] |= *flags;\n        if (crt != NULL) {\n            mbedtls_x509_dn_gets(s_tls15m_subject[depth], sizeof(s_tls15m_subject[depth]), &crt->subject);\n            mbedtls_x509_dn_gets(s_tls15m_issuer[depth], sizeof(s_tls15m_issuer[depth]), &crt->issuer);\n        }\n    }\n    return 0;\n}'''
if new not in s:
    if old not in s: raise RuntimeError('15M: exact 15J callback anchor missing')
    s=s.replace(old,new,1)
reset='''    for (int i=0;i<TLS15M_MAX_DEPTH;i++) {\n        s_tls15m_depth_flags[i]=0; s_tls15m_subject[i][0]='\\0'; s_tls15m_issuer[i][0]='\\0';\n    }\n'''
ranchor='    s_tls15j_verify_depth = -1;\n'
if reset not in s:
    if ranchor not in s: raise RuntimeError('15M reset anchor missing')
    s=s.replace(ranchor,ranchor+reset,1)
for token in ('MBEDTLS_SSL_VERIFY_REQUIRED','mbedtls_x509_dn_gets','s_tls15m_depth_flags'):
    if token not in s: raise RuntimeError('15M invariant missing: '+token)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')
print('15M chain probe installed; verification remains fail-closed')
