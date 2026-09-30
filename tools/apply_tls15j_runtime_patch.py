#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

if 'gTls15iLastError' not in s:
    raise SystemExit('15J requires complete 15I runtime first')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s:
    raise SystemExit('15J CA verification invariant missing')

inc='#include <mbedtls/x509_crt.h>\n'
if inc not in s:
    anchor='#include <mbedtls/md.h>\n'
    if anchor not in s: raise SystemExit('15J mbedTLS include anchor missing')
    s=s.replace(anchor,anchor+inc,1)

# Getter declarations are injected into framework ssl_client.h by the PlatformIO
# pre-script, but declare them here too to make the dependency explicit.
decl='''\nextern uint32_t tls15j_get_verify_flags(void);\nextern int tls15j_get_verify_depth(void);\n'''
if 'extern uint32_t tls15j_get_verify_flags' not in s:
    anchor='PowerStreamApiState psApiState;\n'
    if anchor not in s: raise SystemExit('15J declaration anchor missing')
    s=s.replace(anchor,anchor+decl,1)

atom='''\nstatic std::atomic<uint32_t> gTls15jVerifyFlags{0};\nstatic std::atomic<int32_t> gTls15jVerifyDepth{-1};\nstatic const char* TLS15J_VERSION="9.36.7.15J-X509-VERIFY-FLAGS";\n'''
anchor='static const char* TLS15I_VERSION="9.36.7.15I-X509-ROOTCAUSE";\n'
if 'gTls15jVerifyFlags' not in s:
    if anchor not in s: raise SystemExit('15J atomic anchor missing')
    s=s.replace(anchor,anchor+atom,1)

# Capture immediately after GET returns. The framework hook stores flags globally
# before WiFiClientSecure::connect() performs stop()/context cleanup.
needle='httpCode=http.GET();'
if needle not in s:
    needle='http.GET();'
pos=s.find(needle)
if pos < 0 or s.find(needle,pos+1)>=0:
    raise SystemExit('15J unique GET anchor missing')
cap='''\n  gTls15jVerifyFlags.store(tls15j_get_verify_flags(),std::memory_order_relaxed);\n  gTls15jVerifyDepth.store(tls15j_get_verify_depth(),std::memory_order_relaxed);'''
if 'gTls15jVerifyFlags.store' not in s:
    s=s[:pos+len(needle)]+cap+s[pos+len(needle):]

json_anchor='\\"tls15i_version\\":\\\""+String(TLS15I_VERSION)+"\\\",'
if json_anchor not in s: raise SystemExit('15J JSON anchor missing')
fields='''\\"tls15j_version\\":\\\""+String(TLS15J_VERSION)+"\\\",\\"tls15j_verify_flags_raw\\":"+String(gTls15jVerifyFlags.load())+",\\"tls15j_verify_flags_hex\\":\\\"0x"+String(gTls15jVerifyFlags.load(),HEX)+"\\\",\\"tls15j_verify_depth\\":"+String(gTls15jVerifyDepth.load())+",\\"tls15j_expired\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_EXPIRED)?"true":"false")+",\\"tls15j_revoked\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_REVOKED)?"true":"false")+",\\"tls15j_cn_mismatch\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_CN_MISMATCH)?"true":"false")+",\\"tls15j_not_trusted\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_NOT_TRUSTED)?"true":"false")+",\\"tls15j_future\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_FUTURE)?"true":"false")+",\\"tls15j_bad_md\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_BAD_MD)?"true":"false")+",\\"tls15j_bad_pk\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_BAD_PK)?"true":"false")+",\\"tls15j_bad_key\\":"+((gTls15jVerifyFlags.load()&MBEDTLS_X509_BADCERT_BAD_KEY)?"true":"false")+",'''
if '\\"tls15j_version\\"' not in s:
    s=s.replace(json_anchor,fields+json_anchor,1)

for token in ('tls15j_verify_flags_raw','MBEDTLS_X509_BADCERT_NOT_TRUSTED','MBEDTLS_X509_BADCERT_CN_MISMATCH','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if token not in s: raise SystemExit('15J required token missing: '+token)

# Update generated runtime provenance only; the source baseline remains untouched.
s=s.replace('9.36.7.15I-X509-ROOTCAUSE','9.36.7.15J-X509-VERIFY-FLAGS')
p.write_text(s,encoding='utf-8')

cfg=Path('include/config.h'); c=cfg.read_text(encoding='utf-8')
c=c.replace('2.4.5.9.36.7.15I-X509-ROOTCAUSE','2.4.5.9.36.7.15J-X509-VERIFY-FLAGS')
cfg.write_text(c,encoding='utf-8')
Path('data/fs_version.txt').write_text('2.4.5.9.36.7.15J-X509-VERIFY-FLAGS\n',encoding='utf-8')
print('15J runtime verify-flag telemetry applied; TLS verification remains fail-closed')
