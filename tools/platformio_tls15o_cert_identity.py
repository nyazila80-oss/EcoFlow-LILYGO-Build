#!/usr/bin/env python3
Import('env')
from pathlib import Path
pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15O: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('s_tls15n_raw_len','tls15j_verify_cb','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15O requires 15N state: '+t)
decl='''\n// 15O observation-only certificate identity/crypto telemetry.\nconst char* tls15o_get_serial(int depth);\nconst char* tls15o_get_ski(int depth);\nconst char* tls15o_get_aki(int depth);\nconst char* tls15o_get_sig_oid(int depth);\nsize_t tls15o_get_pk_raw_len(int depth);\n'''
if 'tls15o_get_serial' not in h: h += decl
storage=r'''
static char s_tls15o_serial[TLS15M_MAX_DEPTH][96]={{0}};
static char s_tls15o_ski[TLS15M_MAX_DEPTH][128]={{0}};
static char s_tls15o_aki[TLS15M_MAX_DEPTH][128]={{0}};
static char s_tls15o_sig_oid[TLS15M_MAX_DEPTH][96]={{0}};
static volatile size_t s_tls15o_pk_raw_len[TLS15M_MAX_DEPTH]={0};
static void tls15o_hex(char *out,size_t outsz,const unsigned char *p,size_t n){
 if(!out||outsz==0)return; out[0]='\0'; if(!p)return; size_t w=0;
 static const char hx[]="0123456789abcdef";
 for(size_t i=0;i<n && w+2<outsz;i++){out[w++]=hx[(p[i]>>4)&15];out[w++]=hx[p[i]&15];} out[w]='\0';
}
const char* tls15o_get_serial(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15o_serial[d]:"";}
const char* tls15o_get_ski(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15o_ski[d]:"";}
const char* tls15o_get_aki(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15o_aki[d]:"";}
const char* tls15o_get_sig_oid(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15o_sig_oid[d]:"";}
size_t tls15o_get_pk_raw_len(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15o_pk_raw_len[d]:0;}
'''
a='static char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\n'
if 's_tls15o_serial' not in s:
 if a not in s: raise RuntimeError('15O storage anchor missing')
 s=s.replace(a,storage+a,1)
old="            s_tls15n_raw_len[depth]=crt->raw.len;"
new=r'''            s_tls15n_raw_len[depth]=crt->raw.len;
            tls15o_hex(s_tls15o_serial[depth],sizeof(s_tls15o_serial[depth]),crt->serial.p,crt->serial.len);
            tls15o_hex(s_tls15o_ski[depth],sizeof(s_tls15o_ski[depth]),crt->subject_key_id.p,crt->subject_key_id.len);
            tls15o_hex(s_tls15o_aki[depth],sizeof(s_tls15o_aki[depth]),crt->authority_key_id.keyIdentifier.p,crt->authority_key_id.keyIdentifier.len);
            if (crt->sig_oid.p && crt->sig_oid.len) {
                size_t n=crt->sig_oid.len; if(n>30)n=30;
                tls15o_hex(s_tls15o_sig_oid[depth],sizeof(s_tls15o_sig_oid[depth]),crt->sig_oid.p,n);
            }
            s_tls15o_pk_raw_len[depth]=crt->pk_raw.len;'''
if new not in s:
 if old not in s: raise RuntimeError('15O callback anchor missing')
 s=s.replace(old,new,1)
oldr="s_tls15n_verify_info[i][0]='\\0'; s_tls15n_raw_len[i]=0;"
newr=oldr+" s_tls15o_serial[i][0]='\\0'; s_tls15o_ski[i][0]='\\0'; s_tls15o_aki[i][0]='\\0'; s_tls15o_sig_oid[i][0]='\\0'; s_tls15o_pk_raw_len[i]=0;"
if newr not in s:
 if oldr not in s: raise RuntimeError('15O reset anchor missing')
 s=s.replace(oldr,newr,1)
for t in ('MBEDTLS_SSL_VERIFY_REQUIRED','s_tls15o_ski','authority_key_id.keyIdentifier','crt->pk_raw.len'):
 if t not in s: raise RuntimeError('15O invariant missing: '+t)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')
print('15O certificate identity/crypto probe installed; verification remains fail-closed')
