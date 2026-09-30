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
// Minimal read-only DER walker for X.509 Extensions. It never changes mbedTLS state.
static bool tls15o_der_len(const unsigned char *&p,const unsigned char *end,size_t &n){
 if(!p||p>=end)return false; unsigned char b=*p++;
 if((b&0x80)==0){n=b;return n<=(size_t)(end-p);}
 size_t k=b&0x7f; if(k==0||k>sizeof(size_t)||k>(size_t)(end-p))return false;
 n=0; for(size_t i=0;i<k;i++){if(n>(SIZE_MAX>>8))return false;n=(n<<8)|*p++;}
 return n<=(size_t)(end-p);
}
static bool tls15o_der_tlv(const unsigned char *&p,const unsigned char *end,unsigned char tag,const unsigned char *&v,size_t &n){
 if(!p||p>=end||*p++!=tag)return false; if(!tls15o_der_len(p,end,n))return false; v=p; p+=n; return true;
}
static void tls15o_parse_key_ids(const mbedtls_x509_crt *crt,char *ski,size_t skis,char *aki,size_t akis){
 if(ski&&skis)ski[0]='\0'; if(aki&&akis)aki[0]='\0';
 if(!crt||!crt->v3_ext.p||!crt->v3_ext.len)return;
 const unsigned char *p=crt->v3_ext.p,*end=p+crt->v3_ext.len,*seq=nullptr; size_t sl=0;
 // Depending on mbedTLS version v3_ext may include the outer SEQUENCE or its contents.
 if(p<end&&*p==0x30){const unsigned char *q=p; if(!tls15o_der_tlv(q,end,0x30,seq,sl))return; p=seq; end=seq+sl;}
 while(p<end){
  const unsigned char *ext=nullptr; size_t el=0; if(!tls15o_der_tlv(p,end,0x30,ext,el))break;
  const unsigned char *e=ext,*ee=ext+el,*oid=nullptr; size_t ol=0; if(!tls15o_der_tlv(e,ee,0x06,oid,ol))continue;
  if(e<ee&&*e==0x01){const unsigned char *bv=nullptr;size_t bl=0;if(!tls15o_der_tlv(e,ee,0x01,bv,bl))continue;}
  const unsigned char *ov=nullptr;size_t on=0;if(!tls15o_der_tlv(e,ee,0x04,ov,on))continue;
  const bool is_ski=(ol==3&&oid[0]==0x55&&oid[1]==0x1d&&oid[2]==0x0e);
  const bool is_aki=(ol==3&&oid[0]==0x55&&oid[1]==0x1d&&oid[2]==0x23);
  if(is_ski){const unsigned char *x=ov,*xe=ov+on,*kv=nullptr;size_t kn=0;if(tls15o_der_tlv(x,xe,0x04,kv,kn))tls15o_hex(ski,skis,kv,kn);}
  if(is_aki){const unsigned char *x=ov,*xe=ov+on,*sq=nullptr;size_t qn=0;if(tls15o_der_tlv(x,xe,0x30,sq,qn)){const unsigned char *y=sq,*ye=sq+qn;while(y<ye){unsigned char tag=*y;const unsigned char *kv=nullptr;size_t kn=0;if(!tls15o_der_tlv(y,ye,tag,kv,kn))break;if(tag==0x80){tls15o_hex(aki,akis,kv,kn);break;}}}}
 }
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
            tls15o_parse_key_ids(crt,s_tls15o_ski[depth],sizeof(s_tls15o_ski[depth]),s_tls15o_aki[depth],sizeof(s_tls15o_aki[depth]));
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
for t in ('MBEDTLS_SSL_VERIFY_REQUIRED','s_tls15o_ski','tls15o_parse_key_ids','crt->v3_ext','crt->pk_raw.len'):
 if t not in s: raise RuntimeError('15O invariant missing: '+t)
for forbidden in ('crt->subject_key_id','authority_key_id.keyIdentifier'):
 if forbidden in s: raise RuntimeError('15O incompatible mbedTLS member remains: '+forbidden)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')
print('15O certificate identity/crypto probe installed; SKI/AKI parsed read-only from DER v3_ext; verification remains fail-closed')
