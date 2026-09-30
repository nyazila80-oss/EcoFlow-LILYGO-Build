#!/usr/bin/env python3
from pathlib import Path
p=Path('src/powerstream_api.cpp'); s=p.read_text(encoding='utf-8')
for t in ('TLS15M_VERSION="9.36.7.15M-CLEAN-CHAIN-PROBE"','tls15m_chain','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if t not in s: raise SystemExit('15N prerequisite missing: '+t)
if 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' in s: raise SystemExit('15N refuses 15K/15L extra trust anchor')
decl='''extern const char* tls15n_get_verify_info(int depth);\nextern size_t tls15n_get_cert_raw_len(int depth);\n'''
a='extern const char* tls15m_get_issuer(int depth);\n'
if 'tls15n_get_verify_info' not in s:
    if a not in s: raise SystemExit('15N declaration anchor missing')
    s=s.replace(a,a+decl,1)
a='static const char* TLS15M_VERSION="9.36.7.15M-CLEAN-CHAIN-PROBE";\n'
if 'TLS15N_VERSION' not in s:
    if a not in s: raise SystemExit('15N version anchor missing')
    s=s.replace(a,a+'static const char* TLS15N_VERSION="9.36.7.15N-LEAF-VERIFY-ROOTCAUSE";\n',1)
# Add compact per-depth decoded verify text and raw certificate lengths after the existing 15M chain.
needle='\\"tls15j_ca_pem_bytes\\":"+String(strlen(ECOFLOW_CA_BUNDLE))+",'
fields='''\\"tls15n_version\\":\\\""+String(TLS15N_VERSION)+"\\\",\\"tls15n_verify_detail\\":["+\n String("{\\\"depth\\\":0,\\\"raw_len\\\":")+String((unsigned)tls15n_get_cert_raw_len(0))+",\\\"info\\\":\\\""+tls15mJsonEscape(tls15n_get_verify_info(0))+"\\\"},"+\n String("{\\\"depth\\\":1,\\\"raw_len\\\":")+String((unsigned)tls15n_get_cert_raw_len(1))+",\\\"info\\\":\\\""+tls15mJsonEscape(tls15n_get_verify_info(1))+"\\\"},"+\n String("{\\\"depth\\\":2,\\\"raw_len\\\":")+String((unsigned)tls15n_get_cert_raw_len(2))+",\\\"info\\\":\\\""+tls15mJsonEscape(tls15n_get_verify_info(2))+"\\\"},"+\n String("{\\\"depth\\\":3,\\\"raw_len\\\":")+String((unsigned)tls15n_get_cert_raw_len(3))+",\\\"info\\\":\\\""+tls15mJsonEscape(tls15n_get_verify_info(3))+"\\\"}],'''
if '\\"tls15n_version\\"' not in s:
    if needle not in s: raise SystemExit('15N JSON anchor missing')
    s=s.replace(needle,fields+needle,1)
p.write_text(s,encoding='utf-8')
print('15N runtime telemetry applied; trust and auth behavior unchanged')
