from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 9.36.7.15H.2: X509/time diagnostic after the existing 15D->15E->15G chain.
# Reject an executable setInsecure() call, but do not false-positive on the
# existing security diagnostic/string that mentions the token itself.
def executable_set_insecure(text: str) -> bool:
    for line in text.splitlines():
        code=line.split('//',1)[0]
        if 'setInsecure(' in code and not code.lstrip().startswith(('#','"',"'")):
            return True
    return False

if executable_set_insecure(s):
    raise SystemExit('15H security regression: executable insecure TLS present')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s:
    raise SystemExit('15H invariant: CA verification anchor missing')

if '#include <time.h>' not in s:
    pos=s.find('#include ')
    if pos < 0: raise SystemExit('15H include anchor missing')
    s=s[:pos]+'#include <time.h>\n'+s[pos:]

anchor='static std::atomic<uint32_t> gTlsInternalGetPostFree{0}, gTlsInternalGetPostLargest{0};'
if anchor not in s: raise SystemExit('15H TLS diagnostic anchor missing')
extra='''
static std::atomic<int64_t> gTlsEpochPre{0};
static std::atomic<int64_t> gTlsEpochPost{0};
static std::atomic<bool> gTlsTimeSanePre{false};
static std::atomic<bool> gTlsTimeSanePost{false};
static std::atomic<uint32_t> gTlsInternalPreVerifyFree{0};
static std::atomic<uint32_t> gTlsInternalPreVerifyLargest{0};
static std::atomic<uint32_t> gTlsInternalPostVerifyFree{0};
static std::atomic<uint32_t> gTlsInternalPostVerifyLargest{0};

static bool tlsEpochSane(time_t t){ return t >= (time_t)1704067200; }
'''
if 'gTlsEpochPre' not in s: s=s.replace(anchor,anchor+extra,1)

get_anchor='tlsInternalSnap(gTlsInternalGetPreFree,gTlsInternalGetPreLargest);'
if get_anchor not in s: raise SystemExit('15H GET pre anchor missing')
pre='''
  const time_t tlsNowPre=time(nullptr);
  gTlsEpochPre=(int64_t)tlsNowPre;
  gTlsTimeSanePre=tlsEpochSane(tlsNowPre);
  gTlsInternalPreVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPreVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);'''
if 'const time_t tlsNowPre=time(nullptr);' not in s: s=s.replace(get_anchor,get_anchor+pre,1)

needle='http.GET();'
pos=s.find(needle)
if pos < 0: raise SystemExit('15H http.GET call missing')
if s.find(needle,pos+1) >= 0: raise SystemExit('15H http.GET call not unique')
post='''
  const time_t tlsNowPost=time(nullptr);
  gTlsEpochPost=(int64_t)tlsNowPost;
  gTlsTimeSanePost=tlsEpochSane(tlsNowPost);
  gTlsInternalPostVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPostVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);'''
if 'const time_t tlsNowPost=time(nullptr);' not in s:
    s=s[:pos+len(needle)]+post+s[pos+len(needle):]

json_anchor='\\"internal_free_pre\\":"+String(gTlsInternalFreePre.load())'
if json_anchor not in s: raise SystemExit('15H status JSON anchor missing')
fields='''\\"tls_epoch_pre\\":"+String((long long)gTlsEpochPre.load())+","+
    "\\"tls_epoch_post\\":"+String((long long)gTlsEpochPost.load())+","+
    "\\"tls_time_sane_pre\\":"+(gTlsTimeSanePre.load()?"true":"false")+","+
    "\\"tls_time_sane_post\\":"+(gTlsTimeSanePost.load()?"true":"false")+","+
    "\\"tls_internal_pre_verify_free\\":"+String(gTlsInternalPreVerifyFree.load())+","+
    "\\"tls_internal_pre_verify_largest\\":"+String(gTlsInternalPreVerifyLargest.load())+","+
    "\\"tls_internal_post_verify_free\\":"+String(gTlsInternalPostVerifyFree.load())+","+
    "\\"tls_internal_post_verify_largest\\":"+String(gTlsInternalPostVerifyLargest.load())+","+
    "'''
if '\\"tls_epoch_pre\\"' not in s: s=s.replace(json_anchor,fields+json_anchor,1)

required=['client.setCACert(ECOFLOW_CA_BUNDLE);','gTlsEpochPre','gTlsTimeSanePre','gTlsInternalPreVerifyFree','gTlsInternalPostVerifyLargest','tls_failed_alloc_count','cred_request_secret_match']
for token in required:
    if token not in s: raise SystemExit('15H required token missing: '+token)
if executable_set_insecure(s): raise SystemExit('15H security regression after patch')

p.write_text(s,encoding='utf-8')
print('15H.2 X509/time/internal-RAM diagnostics applied; CA verification remains enabled')
