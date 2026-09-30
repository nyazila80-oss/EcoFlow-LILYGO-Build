#!/usr/bin/env python3
from pathlib import Path
p=Path('src/powerstream_api.cpp'); s=p.read_text(encoding='utf-8')
if 'tls15j_verify_flags_raw' not in s: raise SystemExit('15L requires 15J runtime telemetry')
if 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' not in s: raise SystemExit('15L requires 15K DigiCert Global Root CA anchor')
if 'DigiCert Global Root G2' not in s: raise SystemExit('15L requires existing DigiCert Global Root G2 anchor')

decl='''\nextern uint32_t tls15l_get_depth_flags(int depth);\nextern const char* tls15l_get_subject(int depth);\nextern const char* tls15l_get_issuer(int depth);\n'''
anchor='extern int tls15j_get_verify_depth(void);\n'
if 'tls15l_get_depth_flags' not in s:
    if anchor not in s: raise SystemExit('15L declaration anchor missing')
    s=s.replace(anchor,anchor+decl,1)

helper='''\nstatic String tls15lJsonEscape(const char* in){\n  String o; if(!in) return o;\n  for(size_t i=0; in[i] && i<191; ++i){ char c=in[i];\n    if(c=='\\\\' || c=='\\"'){ o+='\\\\'; o+=c; }\n    else if((unsigned char)c>=0x20) o+=c;\n  }\n  return o;\n}\n'''
# run_tls15k_patch.py intentionally transforms the 15J version string to 15K
# before this patch runs. Keep the variable name (used by existing JSON) and
# anchor on the actual post-15K value.
anchor='static const char* TLS15J_VERSION="9.36.7.15K-ECOFLOW-TRUST-CHAIN";\n'
if 'tls15lJsonEscape' not in s:
    if anchor not in s: raise SystemExit('15L post-15K version anchor missing')
    s=s.replace(anchor,anchor+'static const char* TLS15L_VERSION="9.36.7.15L-CERT-CHAIN-PROBE";\n'+helper,1)

json_anchor='\\"tls15j_version\\":\\\""+String(TLS15J_VERSION)+"\\\",'
if json_anchor not in s: raise SystemExit('15L JSON anchor missing')
fields='''\\"tls15l_version\\":\\\""+String(TLS15L_VERSION)+"\\\",\\"tls15l_chain\\":["+
    String("{\\\"depth\\\":0,\\\"flags\\\":")+String(tls15l_get_depth_flags(0))+",\\\"subject\\\":\\\""+tls15lJsonEscape(tls15l_get_subject(0))+"\\\",\\\"issuer\\\":\\\""+tls15lJsonEscape(tls15l_get_issuer(0))+"\\\"},"+
    String("{\\\"depth\\\":1,\\\"flags\\\":")+String(tls15l_get_depth_flags(1))+",\\\"subject\\\":\\\""+tls15lJsonEscape(tls15l_get_subject(1))+"\\\",\\\"issuer\\\":\\\""+tls15lJsonEscape(tls15l_get_issuer(1))+"\\\"},"+
    String("{\\\"depth\\\":2,\\\"flags\\\":")+String(tls15l_get_depth_flags(2))+",\\\"subject\\\":\\\""+tls15lJsonEscape(tls15l_get_subject(2))+"\\\",\\\"issuer\\\":\\\""+tls15lJsonEscape(tls15l_get_issuer(2))+"\\\"},"+
    String("{\\\"depth\\\":3,\\\"flags\\\":")+String(tls15l_get_depth_flags(3))+",\\\"subject\\\":\\\""+tls15lJsonEscape(tls15l_get_subject(3))+"\\\",\\\"issuer\\\":\\\""+tls15lJsonEscape(tls15l_get_issuer(3))+"\\\"}],'''
if '\\"tls15l_version\\"' not in s: s=s.replace(json_anchor,fields+json_anchor,1)

s=s.replace('9.36.7.15K-ECOFLOW-TRUST-CHAIN','9.36.7.15L-CERT-CHAIN-PROBE')
p.write_text(s,encoding='utf-8')
cfg=Path('include/config.h'); c=cfg.read_text(encoding='utf-8').replace('2.4.5.9.36.7.15K-ECOFLOW-TRUST-CHAIN','2.4.5.9.36.7.15L-CERT-CHAIN-PROBE'); cfg.write_text(c,encoding='utf-8')
Path('data/fs_version.txt').write_text('2.4.5.9.36.7.15L-CERT-CHAIN-PROBE\n',encoding='utf-8')
for t in ('tls15l_chain','tls15l_get_depth_flags','client.setCACert(ECOFLOW_CA_BUNDLE);','MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj','DigiCert Global Root G2'):
    if t not in s: raise SystemExit('15L invariant missing: '+t)
print('15L runtime chain telemetry applied; exact 15K trust anchors retained')
