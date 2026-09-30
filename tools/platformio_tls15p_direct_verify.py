#!/usr/bin/env python3
Import('env')
from pathlib import Path
pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15P: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('tls15o_get_serial','tls15j_verify_cb','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15P requires 15O state: '+t)
# 15P does not weaken TLS. It independently verifies each presented cert signature
# against its issuer public key inside the existing verify callback, exposing whether
# the crypto primitive succeeds even when normal chain building returns NOT_TRUSTED.
decl='''\n// 15P observation/proof: direct certificate-signature verification result.\nint tls15p_get_direct_sig_rc(int depth);\n'''
if 'tls15p_get_direct_sig_rc' not in h: h += decl
storage=r'''
static volatile int s_tls15p_direct_sig_rc[TLS15M_MAX_DEPTH]={-32768,-32768,-32768,-32768};
static mbedtls_x509_crt *s_tls15p_seen[TLS15M_MAX_DEPTH]={nullptr,nullptr,nullptr,nullptr};
int tls15p_get_direct_sig_rc(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15p_direct_sig_rc[d]:-32768;}
static int tls15p_verify_cert_sig(const mbedtls_x509_crt *child,const mbedtls_x509_crt *issuer){
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
            // mbedTLS callbacks arrive leaf->issuer on this observed chain. When an
            // issuer has now arrived, verify the immediately preceding child.
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
for forbidden in ('MBEDTLS_SSL_VERIFY_NONE','setInsecure()'):
 if forbidden in s: raise RuntimeError('15P refuses insecure verification: '+forbidden)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')
print('15P direct certificate signature proof installed; normal TLS verification unchanged/fail-closed')
