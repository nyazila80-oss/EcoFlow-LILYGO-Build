#!/usr/bin/env python3
from pathlib import Path
p=Path('src/powerstream_api.cpp'); s=p.read_text(encoding='utf-8')
for t in ('TLS15N_VERSION="9.36.7.15N-LEAF-VERIFY-ROOTCAUSE"','tls15n_verify_detail','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if t not in s: raise SystemExit('15O prerequisite missing: '+t)
if 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' in s: raise SystemExit('15O refuses 15K/15L extra trust anchor')
decl='''extern const char* tls15o_get_serial(int depth);\nextern const char* tls15o_get_ski(int depth);\nextern const char* tls15o_get_aki(int depth);\nextern const char* tls15o_get_sig_oid(int depth);\nextern size_t tls15o_get_pk_raw_len(int depth);\n'''
a='extern size_t tls15n_get_cert_raw_len(int depth);\n'
if 'tls15o_get_serial' not in s:
    if a not in s: raise SystemExit('15O declaration anchor missing')
    s=s.replace(a,a+decl,1)
a='static const char* TLS15N_VERSION="9.36.7.15N-LEAF-VERIFY-ROOTCAUSE";\n'
if 'TLS15O_VERSION' not in s:
    if a not in s: raise SystemExit('15O version anchor missing')
    s=s.replace(a,a+'static const char* TLS15O_VERSION="9.36.7.15O-CERT-IDENTITY-CRYPTO";\n',1)
needle='String("{\\\"depth\\\":3,\\\"raw_len\\\":")+String((unsigned)tls15n_get_cert_raw_len(3))+",\\\"info\\\":\\\""+tls15mJsonEscape(tls15n_get_verify_info(3))+"\\\"}],'
rows=[]
for d in range(4):
    suffix=',' if d < 3 else ']'
    row=(
        ' String("{\\\"depth\\\":'+str(d)+',\\\"serial\\\":\\\"")'
        '+tls15mJsonEscape(tls15o_get_serial('+str(d)+'))'
        '+"\\\",\\\"ski\\\":\\\""+tls15mJsonEscape(tls15o_get_ski('+str(d)+'))'
        '+"\\\",\\\"aki\\\":\\\""+tls15mJsonEscape(tls15o_get_aki('+str(d)+'))'
        '+"\\\",\\\"sig_oid_hex\\\":\\\""+tls15mJsonEscape(tls15o_get_sig_oid('+str(d)+'))'
        '+"\\\",\\\"pk_raw_len\\\":"+String((unsigned)tls15o_get_pk_raw_len('+str(d)+'))'
        '+"}'+suffix+'"'
    )
    rows.append(row)
extra=(needle+'\\"tls15o_version\\":\\\""+String(TLS15O_VERSION)+"\\\",\\"tls15o_cert_identity\\":["+\n'
       + '+\n'.join(rows) + ',')
if '\\"tls15o_version\\"' not in s:
    if needle not in s: raise SystemExit('15O JSON anchor missing')
    s=s.replace(needle,extra,1)
p.write_text(s,encoding='utf-8')
print('15O runtime certificate identity telemetry applied; trust/auth unchanged')
