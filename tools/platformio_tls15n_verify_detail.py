#!/usr/bin/env python3
Import('env')
from pathlib import Path
pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15N: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for token in ('tls15m_get_depth_flags','tls15j_verify_cb','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if token not in h+s: raise RuntimeError('15N requires 15M framework state: '+token)
decl='''\n// 15N observation-only verification details.\nconst char* tls15n_get_verify_info(int depth);\nsize_t tls15n_get_cert_raw_len(int depth);\n'''
if 'tls15n_get_verify_info' not in h: h += decl
storage='''\nstatic char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\nstatic volatile size_t s_tls15n_raw_len[TLS15M_MAX_DEPTH] = {0};\nconst char* tls15n_get_verify_info(int d){ return (d>=0 && d<TLS15M_MAX_DEPTH)?s_tls15n_verify_info[d]:""; }\nsize_t tls15n_get_cert_raw_len(int d){ return (d>=0 && d<TLS15M_MAX_DEPTH)?s_tls15n_raw_len[d]:0; }\n'''
anchor='const char* tls15m_get_issuer(int d){ return (d>=0 && d<TLS15M_MAX_DEPTH)?s_tls15m_issuer[d]:""; }\n'
if 's_tls15n_verify_info' not in s:
    if anchor not in s: raise RuntimeError('15N storage anchor missing')
    s=s.replace(anchor,anchor+storage,1)
old='''        if (flags != NULL) s_tls15m_depth_flags[depth] |= *flags;\n        if (crt != NULL) {\n            mbedtls_x509_dn_gets(s_tls15m_subject[depth], sizeof(s_tls15m_subject[depth]), &crt->subject);\n            mbedtls_x509_dn_gets(s_tls15m_issuer[depth], sizeof(s_tls15m_issuer[depth]), &crt->issuer);\n        }'''
new='''        if (flags != NULL) {\n            s_tls15m_depth_flags[depth] |= *flags;\n            s_tls15n_verify_info[depth][0]='\\0';\n            mbedtls_x509_crt_verify_info(s_tls15n_verify_info[depth], sizeof(s_tls15n_verify_info[depth]), "", *flags);\n        }\n        if (crt != NULL) {\n            mbedtls_x509_dn_gets(s_tls15m_subject[depth], sizeof(s_tls15m_subject[depth]), &crt->subject);\n            mbedtls_x509_dn_gets(s_tls15m_issuer[depth], sizeof(s_tls15m_issuer[depth]), &crt->issuer);\n            s_tls15n_raw_len[depth]=crt->raw.len;\n        }'''
if new not in s:
    if old in s:
        s=s.replace(old,new,1)
    elif all(t in s for t in ('s_tls15n_verify_info','s_tls15n_raw_len','mbedtls_x509_crt_verify_info')):
        print('15N callback already instrumented; preserving existing verify-detail probe')
    else:
        raise RuntimeError('15N callback anchor missing and installed 15N state incomplete')
r='''        s_tls15m_depth_flags[i]=0; s_tls15m_subject[i][0]='\\0'; s_tls15m_issuer[i][0]='\\0';'''
rn='''        s_tls15m_depth_flags[i]=0; s_tls15m_subject[i][0]='\\0'; s_tls15m_issuer[i][0]='\\0'; s_tls15n_verify_info[i][0]='\\0'; s_tls15n_raw_len[i]=0;'''
if rn not in s:
    if r not in s: raise RuntimeError('15N reset anchor missing')
    s=s.replace(r,rn,1)
for t in ('MBEDTLS_SSL_VERIFY_REQUIRED','mbedtls_x509_crt_verify_info','s_tls15n_raw_len'):
    if t not in s: raise RuntimeError('15N invariant missing: '+t)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')
print('15N verify-detail probe installed/idempotent; verification remains fail-closed')
