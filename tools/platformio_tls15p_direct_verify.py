#!/usr/bin/env python3
Import('env')
from pathlib import Path
pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15P: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('tls15o_get_serial','tls15j_verify_cb','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15P requires 15O state: '+t)
ca_branch='''} else if (rootCABuff != NULL) {'''
verify_required='mbedtls_ssl_conf_authmode(&ssl_client->ssl_conf, MBEDTLS_SSL_VERIFY_REQUIRED);'
if ca_branch not in s or verify_required not in s: raise RuntimeError('15P: expected verified rootCABuff branch missing')
ca_pos=s.index(ca_branch); req_pos=s.index(verify_required,ca_pos); next_branch=s.find('} else if (',ca_pos+len(ca_branch))
if next_branch < 0 or not (ca_pos < req_pos < next_branch): raise RuntimeError('15P: VERIFY_REQUIRED is not scoped to rootCABuff/setCACert branch')
decl='''\n// 15P observation/proof: direct certificate-signature verification result.\nint tls15p_get_direct_sig_rc(int depth);\n'''
if 'tls15p_get_direct_sig_rc' not in h: h += decl
storage=r'''
static volatile int s_tls15p_direct_sig_rc[TLS15M_MAX_DEPTH]={-32768,-32768,-32768,-32768};
static mbedtls_x509_crt *s_tls15p_seen[TLS15M_MAX_DEPTH]={nullptr,nullptr,nullptr,nullptr};
int tls15p_get_direct_sig_rc(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15p_direct_sig_rc[d]:-32768;}
static int tls15p_verify_cert_sig(const mbedtls_x509_crt *child,mbedtls_x509_crt *issuer){
 if(!child||!issuer||!child->tbs.p||!child->tbs.len||!child->sig.p||!child->sig.len)return -32767;
 unsigned char hash[64]={0}; const mbedtls_md_info_t *md=mbedtls_md_info_from_type(child->sig_md);
 if(!md)return -32766; const size_t hlen=mbedtls_md_get_size(md); if(!hlen||hlen>sizeof(hash))return -32765;
 int rc=mbedtls_md(md,child->tbs.p,child->tbs.len,hash); if(rc!=0)return rc;
 return mbedtls_pk_verify_ext(child->sig_pk,&child->sig_opts,&issuer->pk,child->sig_md,hash,hlen,child->sig.p,child->sig.len);
}
'''
a='static char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\n'
if 's_tls15p_direct_sig_rc' not in s:
 if a not in s: raise RuntimeError('15P storage anchor missing')
 s=s.replace(a,storage+a,1)
old='            s_tls15o_pk_raw_len[depth]=crt->pk_raw.len;'
new=old+r'''
            s_tls15p_seen[depth]=crt;
            if(depth>0 && depth<TLS15M_MAX_DEPTH && s_tls15p_seen[depth-1])
                s_tls15p_direct_sig_rc[depth-1]=tls15p_verify_cert_sig(s_tls15p_seen[depth-1],crt);'''
if new not in s:
 if old not in s: raise RuntimeError('15P callback anchor missing')
 s=s.replace(old,new,1)
oldr="s_tls15n_verify_info[i][0]='\\0'; s_tls15n_raw_len[i]=0;"
newr=oldr+" s_tls15p_direct_sig_rc[i]=-32768; s_tls15p_seen[i]=nullptr;"
if newr not in s:
 if oldr not in s: raise RuntimeError('15P reset anchor missing')
 s=s.replace(oldr,newr,1)
for required in ('MBEDTLS_SSL_VERIFY_REQUIRED','mbedtls_pk_verify_ext','tls15p_direct_sig_rc'):
 if required not in h+s: raise RuntimeError('15P invariant missing: '+required)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')

# Expose proof values through the already-used /api/powerstream/job JSON.
# The prior 15J/O scripts patch this project source during the same pre-script chain.
proj=Path(env['PROJECT_DIR'])/'src'/'powerstream_api.cpp'
p=proj.read_text(encoding='utf-8')
if '#include <WiFiClientSecure.h>' not in p: raise RuntimeError('15P project anchor missing')
if 'tls15p_direct_sig_rc' not in p:
    p=p.replace('#include <WiFiClientSecure.h>','#include <WiFiClientSecure.h>\nextern int tls15p_get_direct_sig_rc(int depth);',1)
    anchor=',\\\"tls15o_version\\\":\\\"9.36.7.15O-CERT-IDENTITY-CRYPTO\\\"'
    if anchor not in p: raise RuntimeError('15P JSON anchor missing after 15O patch')
    insert=',\\\"tls15p_version\\\":\\\"9.36.7.15P-DIRECT-SIG-PROOF\\\",\\\"tls15p_direct_sig_rc\\\":['+'+String(tls15p_get_direct_sig_rc(0))+","+String(tls15p_get_direct_sig_rc(1))+","+String(tls15p_get_direct_sig_rc(2))+","+String(tls15p_get_direct_sig_rc(3))+"],"+'
    p=p.replace(anchor,insert+anchor,1)
proj.write_text(p,encoding='utf-8')
print('15P direct signature proof + job JSON telemetry installed; setCACert/rootCABuff remains VERIFY_REQUIRED')
