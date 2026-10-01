#!/usr/bin/env python3
Import('env')
from pathlib import Path

pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15Y: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('tls15x_get_pair_class','s_tls15p_seen','tls15r_get_plain_rc','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15Y requires 15X/P/R state: '+t)

decl='''
// 15Y differential crypto/memory root-cause probe. Observation-only.
int tls15y_get_rsa_direct_rc(int depth);
int tls15y_get_internal_free_pre(int depth);
int tls15y_get_internal_largest_pre(int depth);
int tls15y_get_internal_free_post(int depth);
int tls15y_get_internal_largest_post(int depth);
int tls15y_get_class(int depth);
'''
if 'tls15y_get_rsa_direct_rc' not in h: h += decl

storage=r'''
static volatile int s_tls15y_rsa_direct_rc[TLS15M_MAX_DEPTH]={-32768,-32768,-32768,-32768};
static volatile int s_tls15y_internal_free_pre[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15y_internal_largest_pre[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15y_internal_free_post[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15y_internal_largest_post[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15y_class[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
int tls15y_get_rsa_direct_rc(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15y_rsa_direct_rc[d]:-32768;}
int tls15y_get_internal_free_pre(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15y_internal_free_pre[d]:-1;}
int tls15y_get_internal_largest_pre(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15y_internal_largest_pre[d]:-1;}
int tls15y_get_internal_free_post(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15y_internal_free_post[d]:-1;}
int tls15y_get_internal_largest_post(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15y_internal_largest_post[d]:-1;}
int tls15y_get_class(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15y_class[d]:-1;}
static void tls15y_probe_pair(int d){
 if(d<0||d>=TLS15M_MAX_DEPTH-1||!s_tls15p_seen[d]||!s_tls15p_seen[d+1])return;
 const mbedtls_x509_crt *c=s_tls15p_seen[d]; mbedtls_x509_crt *iss=s_tls15p_seen[d+1];
 const uint32_t caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;
 s_tls15y_internal_free_pre[d]=(int)heap_caps_get_free_size(caps);
 s_tls15y_internal_largest_pre[d]=(int)heap_caps_get_largest_free_block(caps);
 const mbedtls_md_info_t *md=mbedtls_md_info_from_type(c->sig_md);
 int rc=-32768;
 if(md){
   unsigned char hash[MBEDTLS_MD_MAX_SIZE]={0}; size_t n=mbedtls_md_get_size(md);
   if(n>0&&n<=sizeof(hash)&&mbedtls_md(md,c->tbs.p,c->tbs.len,hash)==0){
     rc=mbedtls_pk_verify(&iss->pk,c->sig_md,hash,n,c->sig.p,c->sig.len);
   }
 }
 s_tls15y_rsa_direct_rc[d]=rc;
 s_tls15y_internal_free_post[d]=(int)heap_caps_get_free_size(caps);
 s_tls15y_internal_largest_post[d]=(int)heap_caps_get_largest_free_block(caps);
 // 0=direct PASS; 1=crypto/data fail with >=8K largest internal; 2=memory-pressure candidate (<8K largest); 3=inconclusive
 if(rc==0)s_tls15y_class[d]=0;
 else if(rc!=-32768 && s_tls15y_internal_largest_pre[d]>=8192)s_tls15y_class[d]=1;
 else if(rc!=-32768 && s_tls15y_internal_largest_pre[d]<8192)s_tls15y_class[d]=2;
 else s_tls15y_class[d]=3;
}
'''
a='static volatile int s_tls15x_hash_repeat_match[TLS15M_MAX_DEPTH]'
if 's_tls15y_rsa_direct_rc' not in s:
    pos=s.find(a)
    if pos<0: raise RuntimeError('15Y storage anchor missing')
    s=s[:pos]+storage+s[pos:]
# Run after 15X so same captured immutable pair is compared.
for old in ('tls15x_probe_pair(depth-1);','tls15x_probe_pair(depth);'):
    new=old+'\n                tls15y_probe_pair(' + ('depth-1' if 'depth-1' in old else 'depth') + ');'
    if new not in s:
        if old not in s: raise RuntimeError('15Y pair anchor missing: '+old)
        s=s.replace(old,new,1)
oldr='s_tls15x_tbs_fp[i]=0; s_tls15x_sig_fp[i]=0; s_tls15x_pk_fp[i]=0;'
newr=oldr+' s_tls15y_rsa_direct_rc[i]=-32768; s_tls15y_internal_free_pre[i]=-1; s_tls15y_internal_largest_pre[i]=-1; s_tls15y_internal_free_post[i]=-1; s_tls15y_internal_largest_post[i]=-1; s_tls15y_class[i]=-1;'
if newr not in s:
    if oldr not in s: raise RuntimeError('15Y reset anchor missing')
    s=s.replace(oldr,newr,1)
if 'MBEDTLS_SSL_VERIFY_REQUIRED' not in s: raise RuntimeError('15Y safety invariant lost')
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')

proj=Path(env['PROJECT_DIR'])/'src'/'powerstream_api.cpp'; p=proj.read_text(encoding='utf-8'); inc='#include <WiFiClientSecure.h>'
extern='''extern int tls15y_get_rsa_direct_rc(int depth);
extern int tls15y_get_internal_free_pre(int depth);
extern int tls15y_get_internal_largest_pre(int depth);
extern int tls15y_get_internal_free_post(int depth);
extern int tls15y_get_internal_largest_post(int depth);
extern int tls15y_get_class(int depth);'''
if extern not in p:
    if inc not in p: raise RuntimeError('15Y include anchor missing')
    p=p.replace(inc,inc+'\n'+extern,1)
field='\\"heavy_owner\\":\\"'
if 'tls15y_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15Y JSON anchor missing')
    def arr(fn): return '"+String('+fn+'(0))+","+String('+fn+'(1))+","+String('+fn+'(2))+","+String('+fn+'(3))+"'
    insert='\\"tls15y_version\\":\\"9.36.7.15Y-DIFFERENTIAL-ROOTCAUSE\\",'
    for key,fn in [('rsa_direct_rc','tls15y_get_rsa_direct_rc'),('internal_free_pre','tls15y_get_internal_free_pre'),('internal_largest_pre','tls15y_get_internal_largest_pre'),('internal_free_post','tls15y_get_internal_free_post'),('internal_largest_post','tls15y_get_internal_largest_post'),('class','tls15y_get_class')]: insert+='\\"tls15y_'+key+'\\":['+arr(fn)+'],'
    p=p[:pos]+insert+p[pos:]
for key in ('tls15y_version','tls15y_rsa_direct_rc','tls15y_internal_free_pre','tls15y_internal_largest_pre','tls15y_internal_free_post','tls15y_internal_largest_post','tls15y_class'):
    if p.count(key)!=1: raise RuntimeError('15Y JSON invariant failed: '+key)
proj.write_text(p,encoding='utf-8')
print('15Y differential crypto/memory probe installed; observation-only; VERIFY_REQUIRED preserved')
